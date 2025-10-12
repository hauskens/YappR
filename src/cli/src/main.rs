use yappr_shared::models::platforms::Platform;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    test_twitch().await?;
    test_youtube().await?;
    Ok(())
}   

async fn test_twitch() -> Result<(), Box<dyn std::error::Error>> {
    let api_client = Platform::Twitch.create_api_client().await?;
    let video = api_client.get_platform_videos_by_ids(&["2568399115".to_string()]).await?;
    println!("Video: {}", video[0].title);
    Ok(())
}

async fn test_youtube() -> Result<(), Box<dyn std::error::Error>> {
    let api_client = Platform::YouTube.create_api_client().await?;
    let video = api_client.get_platform_videos_by_ids(&["8NtaMr2-mRs".to_string()]).await?;
    println!("Video: {}", video[0].title);
    Ok(())
}
