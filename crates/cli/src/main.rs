use tracing::info;
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;
use yappr_shared::config::Config;
use yappr_shared::database::get_database_connection;
use yappr_shared::external::ApiClient;
use yappr_shared::external::{TwitchApiClient, YouTubeApiClient};
use yappr_shared::jobs::{HelloRequest, HelloResponse, NatsClientExt};
use yappr_shared::models::channel::ChannelExt;
use yappr_shared::services::channel::ChannelService;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let _config = Config::load();

    tracing_subscriber::registry()
        .with(tracing_subscriber::fmt::Layer::new())
        .init();

    tracing::info!(
        task = "tracing_setup",
        result = "success",
        "tracing successfully set up with Loki",
    );

    // test_twitch().await?;
    // test_redis().await?;
    // test_youtube().await?;
    // test_channel_service().await?;
    let response = test_nats().await?;
    info!(
        "Response: {}, Timestamp: {}",
        response.message, response.timestamp
    );

    // Give tracing_loki time to flush logs
    tokio::time::sleep(tokio::time::Duration::from_millis(1000)).await;
    Ok(())
}

async fn test_nats() -> Result<HelloResponse, Box<dyn std::error::Error>> {
    let config = Config::load();
    let client = async_nats::connect(config.nats.url.value.as_str()).await?;

    // Create a type-safe job request
    let request = HelloRequest {
        name: "World".to_string(),
    };

    // Use the trait extension to send the request
    // No need to manually specify subject or handle serialization!
    let response = client.request_job(request).await?;

    Ok(response)
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
