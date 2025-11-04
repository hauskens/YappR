use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::process;
use tracing::info;
use tracing_loki;
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;
use yappr_shared::config::Config;
use yappr_shared::database::get_database_connection;
use yappr_shared::entities::sea_orm_active_enums::Videotype;
use yappr_shared::entities::video;
use yappr_shared::external::ApiClient;
use yappr_shared::external::{TwitchApiClient, YouTubeApiClient};
use yappr_shared::models::channel::ChannelExt;
use yappr_shared::redis_client::{Event, RedisClient, StreamType};
use yappr_shared::services::channel::ChannelService;

#[derive(Debug, Clone, Serialize, Deserialize)]
struct TaskPayload {
    task_id: String,
    task_type: String,
    priority: u8,
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let config = Config::load();

    if let Some(loki_url) = config.loki_url {
        println!("Setting up Loki logging with URL: {}", loki_url);
        let (layer, task) = tracing_loki::builder()
            .label("service", config.service_name)
            .unwrap()
            .label("version", config.version.to_string())
            .unwrap()
            .label("environment", config.environment.as_string())
            .unwrap()
            .build_url(loki_url)
            .unwrap();

        tracing_subscriber::registry()
            .with(layer)
            .with(tracing_subscriber::fmt::Layer::new())
            .init();
        tokio::spawn(task);

        tracing::info!(
            task = "tracing_setup",
            result = "success",
            "tracing successfully set up with Loki",
        );
    } else {
        println!("No LOKI_URL configured, using console logging only");
        tracing_subscriber::registry()
            .with(tracing_subscriber::fmt::Layer::new())
            .init();

        tracing::info!(
            task = "tracing_setup",
            result = "success",
            "tracing successfully set up without Loki",
        );
    }

    // test_twitch().await?;
    // test_redis().await?;
    // test_youtube().await?;
    test_channel_service().await?;

    // Give tracing_loki time to flush logs
    tokio::time::sleep(tokio::time::Duration::from_millis(1000)).await;
    Ok(())
}

async fn test_twitch() -> Result<(), Box<dyn std::error::Error>> {
    let api_client = TwitchApiClient::new().await?;
    let video = api_client
        .get_platform_videos_by_ids(&["2568399115".to_string()])
        .await?;
    info!("Video: {}", video[0].title);
    Ok(())
}

async fn test_youtube() -> Result<(), Box<dyn std::error::Error>> {
    let api_client = YouTubeApiClient::new().await?;
    let video = api_client
        .get_platform_videos_by_ids(&["8NtaMr2-mRs".to_string()])
        .await?;
    info!("Video: {}", video[0].title);
    Ok(())
}

async fn test_redis() -> Result<(), Box<dyn std::error::Error>> {
    // Create a Redis client for publishing
    let mut publisher = RedisClient::new("task-processors", "publisher-1").await?;

    info!("Created publisher");

    // Create an event
    let task = TaskPayload {
        task_id: "task-123".to_string(),
        task_type: "transcription".to_string(),
        priority: 5,
    };

    let event = Event::new("task.created", task)
        .with_metadata("source", "api")
        .with_metadata("user_id", "user-456");

    // Publish the event
    let message_id = publisher
        .publish_event("tasks-stream", event.clone())
        .await?;

    info!("Published event with ID: {}", message_id);

    // Create a Redis client for consuming
    let mut consumer = RedisClient::new("task-processors", "worker-1").await?;

    // Consume events (blocking for up to 5 seconds)
    info!("Waiting for events...");
    let events = consumer
        .consume_events::<TaskPayload>("tasks-stream", 10, Some(5000))
        .await?;

    info!("Consumed {} events", events.len());

    for consumed in events {
        info!("Processing event: {:?}", consumed.event);

        // Simulate processing
        match consumed.event.payload.task_type.as_str() {
            "transcription" => {
                info!(
                    "Processing transcription task: {}",
                    consumed.event.payload.task_id
                );

                // Success - acknowledge the event
                consumer.ack(&consumed.stream, &consumed.message_id).await?;
                info!("Successfully processed and acknowledged");
            }
            "unknown" => {
                info!("Unknown task type, rejecting without retry");

                // Permanent failure - nack without retry
                consumer
                    .nack(&consumed.stream, &consumed.message_id, false)
                    .await?;
            }
            _ => {
                info!("Temporary failure, allowing retry");

                // Temporary failure - nack with retry
                consumer
                    .nack(&consumed.stream, &consumed.message_id, true)
                    .await?;
            }
        }
    }

    Ok(())
}

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
