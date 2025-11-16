mod handlers;

use futures::StreamExt;
use tracing::{error, info, instrument, warn};
use yappr_shared::config::Config;
use yappr_shared::jobs::DemoJobRequest;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Initialize logging
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .init();

    // Load configuration
    let config = Config::load();

    // Parse command-line arguments for worker queues
    let args: Vec<String> = std::env::args().collect();
    let queues = parse_queues(&args, &config);

    if queues.is_empty() {
        error!(
            "No valid worker queues specified. Use --queues general,transcription,video or set WORKER_QUEUES env var"
        );
        return Err("No queues specified".into());
    }

    info!(?queues, "Worker starting with queues");

    // Connect to NATS
    let client = async_nats::connect(&config.nats.url.to_string()).await?;

    // Subscribe to job queues with a queue group
    // The queue group ensures only one worker receives each message
    let queue_group = "workers";
    let mut subscribers = Vec::new();

    for queue in &queues {
        let subject = format!("worker.queue.{}", queue);
        let subscriber = client
            .queue_subscribe(subject.clone(), queue_group.to_string())
            .await?;
        info!(
            subject = %subject,
            queue_group = %queue_group,
            queue = %queue,
            "Subscribed to job queue"
        );
        subscribers.push(subscriber);
    }

    // Merge all subscribers into a single stream
    let mut combined_stream = futures::stream::select_all(subscribers);

    info!("Worker ready, waiting for jobs...");

    // Process incoming requests sequentially
    while let Some(message) = combined_stream.next().await {
        if let Err(e) = handle_message(&client, message).await {
            error!(error = %e, "Error handling message");
        }
    }

    Ok(())
}

fn parse_queues(args: &[String], config: &Config) -> Vec<String> {
    let mut queues = Vec::new();

    // First, check CLI arguments
    for (i, arg) in args.iter().enumerate() {
        if arg == "--queues" {
            if let Some(queues_str) = args.get(i + 1) {
                for queue in queues_str.split(',') {
                    let queue = queue.trim().to_string();
                    if !queue.is_empty() {
                        queues.push(queue);
                    }
                }
            }
            break;
        }
    }

    // If no CLI args, use config value
    if queues.is_empty() {
        for queue in config.nats.worker_queues.value.split(',') {
            let queue = queue.trim().to_string();
            if !queue.is_empty() {
                queues.push(queue);
            }
        }
    }

    queues
}

/// Enum representing all possible job types that can be handled
enum JobType {
    Demo(DemoJobRequest),
}

impl JobType {
    /// Try to deserialize the message payload into one of the known job types
    fn from_payload(payload: &[u8]) -> Option<Self> {
        if let Ok(job) = rmp_serde::from_slice::<DemoJobRequest>(payload) {
            return Some(JobType::Demo(job));
        }

        // Add more job type attempts here
        // if let Ok(job) = rmp_serde::from_slice::<TranscriptionJobRequest>(payload) {
        //     return Some(JobType::Transcription(job));
        // }

        None
    }
}

/// Handle an incoming NATS message and route to appropriate handler
#[instrument(skip(client, message))]
async fn handle_message(
    client: &async_nats::Client,
    message: async_nats::Message,
) -> Result<(), Box<dyn std::error::Error>> {
    info!(
        subject = %message.subject,
        reply_to = ?message.reply,
        payload_size = message.payload.len(),
        "Received message"
    );

    // Try to deserialize the message into a known job type
    let job_type = match JobType::from_payload(&message.payload) {
        Some(job) => job,
        None => {
            warn!("Unable to deserialize message to any known job type");
            return Ok(());
        }
    };

    // Dispatch to the appropriate handler based on job type
    match job_type {
        JobType::Demo(request) => {
            let response = handlers::handle_demo_job(client, request).await?;
            send_reply(client, message.reply, response).await?;
        }
    }
    Ok(())
}

/// Send a reply message if reply_to is present
async fn send_reply<T: serde::Serialize>(
    client: &async_nats::Client,
    reply_to: Option<async_nats::Subject>,
    response: T,
) -> Result<(), Box<dyn std::error::Error>> {
    if let Some(reply_subject) = reply_to {
        let response_bytes = rmp_serde::to_vec(&response)?;
        client.publish(reply_subject, response_bytes.into()).await?;
    }
    Ok(())
}
