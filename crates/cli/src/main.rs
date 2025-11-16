use futures::StreamExt;
use tracing::info;
use yappr_shared::config::Config;
use yappr_shared::database::get_database_connection;
use yappr_shared::external::ApiClient;
use yappr_shared::external::{TwitchApiClient, YouTubeApiClient};
use yappr_shared::jobs::{DemoJobRequest, DemoJobResponse, JobError, JobProgress, NatsClientExt};
use yappr_shared::models::channel::ChannelExt;
use yappr_shared::services::channel::ChannelService;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let _config = Config::load();

    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .init();

    tracing::info!(
        task = "tracing_setup",
        result = "success",
        "tracing successfully set up",
    );

    // Test the demo job with progress updates
    test_demo_job().await?;

    // Give tracing time to flush logs
    tokio::time::sleep(tokio::time::Duration::from_millis(1000)).await;
    Ok(())
}

async fn test_demo_job() -> Result<(), JobError> {
    let config = Config::load();
    let client = async_nats::connect(config.nats.url.value.as_str()).await?;

    // Generate unique job ID
    let job_id = uuid::Uuid::new_v4().to_string();
    info!(job_id = %job_id, "Starting demo job test");

    // Subscribe to progress updates for this job
    let progress_subject = format!("worker.progress.{}", job_id);
    let mut progress_subscriber = client.subscribe(progress_subject.clone()).await?;

    info!(subject = %progress_subject, "Subscribed to progress updates");

    // Spawn a task to listen for progress updates
    let progress_task = tokio::spawn(async move {
        info!("Waiting for progress updates...");
        while let Some(message) = progress_subscriber.next().await {
            match rmp_serde::from_slice::<JobProgress>(&message.payload) {
                Ok(progress) => {
                    info!(
                        job_id = %progress.job_id,
                        worker_id = %progress.worker_id,
                        progress = %progress.progress,
                        message = %progress.message,
                        "📊 Progress update"
                    );
                }
                Err(e) => {
                    info!(error = %e, "Failed to deserialize progress update");
                }
            }
        }
    });

    // Create and send the job request
    let request = DemoJobRequest {
        job_id: job_id.clone(),
    };

    info!(
        job_id = %job_id,
        "Sending demo job request"
    );

    // Send the request and wait for response
    let response: DemoJobResponse = client.request_job(request).await?;

    info!(
        job_id = %response.job_id,
        completed_at = response.completed_at,
        "✅ Job completed successfully"
    );

    // Give progress task a moment to process final messages, then cancel it
    tokio::time::sleep(tokio::time::Duration::from_millis(500)).await;
    progress_task.abort();

    Ok(())
}

#[allow(dead_code)]
async fn test_twitch() -> Result<(), Box<dyn std::error::Error>> {
    let api_client = TwitchApiClient::new().await?;
    let video = api_client
        .get_platform_videos_by_ids(&["2568399115".to_string()])
        .await?;
    info!("Video: {}", video[0].title);
    Ok(())
}

#[allow(dead_code)]
async fn test_youtube() -> Result<(), Box<dyn std::error::Error>> {
    let api_client = YouTubeApiClient::new().await?;
    let video = api_client
        .get_platform_videos_by_ids(&["8NtaMr2-mRs".to_string()])
        .await?;
    info!("Video: {}", video[0].title);
    Ok(())
}

#[allow(dead_code)]
async fn test_channel_service() -> Result<(), Box<dyn std::error::Error>> {
    info!("Testing ChannelService");

    // Get database connection
    let db = get_database_connection().await?;
    info!("Database connection established");

    // Example 1: Get all channels
    let all_channels = ChannelService::get_channels_by_broadcaster(&db, 1).await?;
    info!("Found {} total channels", all_channels.len());

    // Print first few channels
    for (i, channel) in all_channels.iter().take(5).enumerate() {
        let videos = channel.get_videos(&db).await?;
        info!("Found {} videos for channel {}", videos.len(), channel.id);
        info!(
            index = i,
            channel_id = channel.id,
            channel_name = channel.name,
            platform = channel.platform_name,
            platform_ref = channel.platform_ref,
            "Channel details"
        );
    }

    info!("ChannelService test completed");
    Ok(())
}
