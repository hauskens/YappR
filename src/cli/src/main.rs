use yappr_shared::external::ApiClient;
use yappr_shared::services::channel::ChannelService;
use yappr_shared::models::channel::Channel;
use yappr_shared::external::TwitchApiClient;
use yappr_shared::external::YouTubeApiClient;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    test_twitch().await?;
    test_youtube().await?;
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
    let video = api_client.get_platform_videos_by_ids(&["2568399115".to_string()]).await?;
    println!("Video: {}", video[0].title);
    Ok(())
}

async fn test_youtube() -> Result<(), Box<dyn std::error::Error>> {
    let api_client = YouTubeApiClient::new().await?;
    let video = api_client.get_platform_videos_by_ids(&["8NtaMr2-mRs".to_string()]).await?;
    println!("Video: {}", video[0].title);
    Ok(())
}
