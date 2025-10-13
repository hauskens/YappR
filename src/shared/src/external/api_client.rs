use serde::{Deserialize, Serialize};
use crate::{entities::sea_orm_active_enums::Videotype, external::twitch::TwitchApiClient};
use crate::external::youtube::YouTubeApiClient;
use std::error::Error;
use async_trait::async_trait;

pub enum PlatformApiClient {
    Twitch(TwitchApiClient),
    YouTube(YouTubeApiClient),
}
#[async_trait]
pub trait ApiClient {
    async fn get_platform_videos_by_ids(&self, video_ids: &[String]) -> Result<Vec<PlatformVideo>, Box<dyn Error>>;
    async fn get_platform_users_by_ids(&self, user_ids: &[String]) -> Result<Vec<PlatformUser>, Box<dyn Error>>;
}
#[async_trait]
impl ApiClient for PlatformApiClient {
    async fn get_platform_videos_by_ids(&self, video_ids: &[String]) -> Result<Vec<PlatformVideo>, Box<dyn Error>> {
        match self {
            PlatformApiClient::Twitch(client) => client.get_platform_videos_by_ids(video_ids).await,
            PlatformApiClient::YouTube(client) => client.get_platform_videos_by_ids(video_ids).await,
        }
    }

    async fn get_platform_users_by_ids(&self, user_ids: &[String]) -> Result<Vec<PlatformUser>, Box<dyn Error>> {
        match self {
            PlatformApiClient::Twitch(client) => client.get_platform_users_by_ids(user_ids).await,
            PlatformApiClient::YouTube(client) => client.get_platform_users_by_ids(user_ids).await,
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
