use std::collections::HashMap;
use std::process;
use tracing::info;
use tracing_loki;
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;
use yappr_shared::config::Config;
use yappr_shared::external::ApiClient;
use yappr_shared::external::{TwitchApiClient, YouTubeApiClient};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let config = Config::load();

    if let Some(loki_url) = config.loki_url {
        println!("Setting up Loki logging with URL: {}", loki_url);
        let (layer, task) = tracing_loki::builder()
            .label("service", config.service_name).unwrap()
            .label("version", config.version.to_string()).unwrap()
            .label("environment", config.environment.as_string()).unwrap()
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

    test_twitch().await?;
    // test_youtube().await?;

    // Give tracing_loki time to flush logs
    tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;
    Ok(())
    // let channel_service = ChannelService::new().await;
    // let channel = channel_service.get_by_id(7).await;
    // println!("Channel: {:#?}", channel);
    // if let Ok(Some(channel)) = channel {
    //     // These methods are available from the Channel trait implementation
    //     let platform = channel.platform();  // Returns Platform enum
    //     let url = channel.channel_url();     // Returns the formatted channel URL
    //     println!("Platform: {:?}, URL: {}", platform, url);
    // }
    // Ok(())
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
