use futures::StreamExt;
use tracing::{error, info, instrument};
use yappr_shared::config::Config;
use yappr_shared::jobs::{HelloRequest, HelloResponse};

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

    // Connect to NATS
    let client = async_nats::connect(&config.nats.url.to_string()).await?;
    info!("Connected to NATS server");

    // Subscribe to the hello worker subject
    let subject = "worker.hello";
    let mut subscriber = client.subscribe(subject.to_string()).await?;
    info!(subject = %subject, "Subscribed to subject, waiting for requests...");

    // Process incoming requests
    while let Some(message) = subscriber.next().await {
        if let Err(e) = handle_request(&client, message).await {
            error!(error = %e, "Error handling request");
        }
    }

    Ok(())
}

#[instrument(skip(client, message))]
async fn handle_request(
    client: &async_nats::Client,
    message: async_nats::Message,
) -> Result<(), Box<dyn std::error::Error>> {
    // Deserialize the request
    let request: HelloRequest = rmp_serde::from_slice(&message.payload)?;

    info!(
        name = %request.name,
        reply_to = ?message.reply,
        "Hello, world! Received request"
    );

    // wait for 5 seconds
    tokio::time::sleep(tokio::time::Duration::from_secs(30)).await;

    // Create typed response
    let response = HelloResponse {
        message: format!("Hello, {}!", request.name),
        timestamp: chrono::Utc::now().timestamp(),
    };

    // Serialize and send reply if reply_to is present
    if let Some(reply_to) = message.reply {
        let response_bytes = rmp_serde::to_vec(&response)?;
        client.publish(reply_to, response_bytes.into()).await?;
        info!(message = %response.message, "Sent reply");
    }

    Ok(())
}
