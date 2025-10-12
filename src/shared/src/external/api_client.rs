use serde::{Deserialize, Serialize};
use crate::{entities::sea_orm_active_enums::Videotype, external::twitch::TwitchApiClient};
use std::error::Error;

pub enum PlatformApiClient {
    Twitch(TwitchApiClient),
}
pub trait ApiClient {
    fn get_platform_videos_by_ids(&self, video_ids: &[String]) -> impl std::future::Future<Output = Result<Vec<PlatformVideo>, Box<dyn Error>>> + Send;
    fn get_platform_users_by_ids(&self, user_ids: &[String]) -> impl std::future::Future<Output = Result<Vec<PlatformUser>, Box<dyn Error>>> + Send;
}
impl ApiClient for PlatformApiClient {
    fn get_platform_videos_by_ids(
        &self,
        video_ids: &[String],
    ) -> impl std::future::Future<Output = Result<Vec<PlatformVideo>, Box<dyn Error>>> + Send {
        match self {
            PlatformApiClient::Twitch(client) => client.get_platform_videos_by_ids(video_ids),
        }
    }
    fn get_platform_users_by_ids(
        &self,
        user_ids: &[String],
    ) -> impl std::future::Future<Output = Result<Vec<PlatformUser>, Box<dyn Error>>> + Send {
        match self {
            PlatformApiClient::Twitch(client) => client.get_platform_users_by_ids(user_ids),
        }
    }
}

impl PlatformApiClient {
    pub async fn get_platform_videos_by_ids(
        &self,
        video_ids: &[String],
    ) -> Result<Vec<PlatformVideo>, Box<dyn Error>> {
        ApiClient::get_platform_videos_by_ids(self, video_ids).await
    }
    pub async fn get_platform_users_by_ids(
        &self,
        user_ids: &[String],
    ) -> Result<Vec<PlatformUser>, Box<dyn Error>> {
        ApiClient::get_platform_users_by_ids(self, user_ids).await
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
