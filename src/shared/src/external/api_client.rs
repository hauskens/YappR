use eyre::Result;
use serde::{Deserialize, Serialize};
use crate::{entities::sea_orm_active_enums::Videotype, external::twitch::TwitchApiClient, models::platforms::Platform};

/// Platform-agnostic API client enum
pub enum PlatformApiClient {
    Twitch(TwitchApiClient),
    // YouTube(YouTubeApiClient), // Future implementation
}

impl PlatformApiClient {
    pub fn platform(&self) -> Platform {
        match self {
            PlatformApiClient::Twitch(_) => Platform::Twitch,
            // PlatformApiClient::YouTube(_) => Platform::YouTube,
        }
    }
    pub async fn get_video(&self, video_id: &str) -> Result<PlatformVideo> {
        match self {
            PlatformApiClient::Twitch(client) => {
                let videos = client.get_platform_video_by_ids(&[video_id.to_string()]).await?;
                Ok(videos[0].clone())
            }
        }
    }
    

}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlatformUser {
    pub id: String,
    pub display_name: String,
    pub profile_image_url: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlatformVideo {
    pub id: String,
    pub title: String,
    pub duration: Option<std::time::Duration>,
    pub created_at: chrono::DateTime<chrono::Utc>,
    pub thumbnail_url: Option<String>,
    pub view_count: Option<u64>,
    pub video_type: Videotype,
}
