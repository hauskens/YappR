use crate::external::youtube::YouTubeApiClient;
use crate::{entities::sea_orm_active_enums::Videotype, external::twitch::TwitchApiClient};
use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use std::error::Error;
use tracing::{error, info, instrument};

pub enum PlatformApiClient {
    Twitch(TwitchApiClient),
    YouTube(YouTubeApiClient),
}
#[async_trait]
pub trait ApiClient: Send + Sync {
    async fn get_platform_videos_by_ids(
        &self,
        video_ids: &[String],
    ) -> Result<Vec<PlatformVideo>, Box<dyn Error>>;
    async fn get_platform_users_by_ids(
        &self,
        user_ids: &[String],
    ) -> Result<Vec<PlatformUser>, Box<dyn Error>>;
}
#[async_trait]
impl ApiClient for PlatformApiClient {
    #[instrument(level = "info", skip(self, video_ids))]
    async fn get_platform_videos_by_ids(
        &self,
        video_ids: &[String],
    ) -> Result<Vec<PlatformVideo>, Box<dyn Error>> {
        let platform = match self {
            PlatformApiClient::Twitch(_) => "twitch",
            PlatformApiClient::YouTube(_) => "youtube",
        };

        info!(
            platform = platform,
            video_count = video_ids.len(),
            "Fetching platform videos by IDs"
        );

        let result = match self {
            PlatformApiClient::Twitch(client) => client.get_platform_videos_by_ids(video_ids).await,
            PlatformApiClient::YouTube(client) => {
                client.get_platform_videos_by_ids(video_ids).await
            }
        };

        match &result {
            Ok(videos) => {
                info!(
                    platform = platform,
                    requested_count = video_ids.len(),
                    returned_count = videos.len(),
                    "Successfully fetched platform videos"
                );
            }
            Err(e) => {
                error!(
                    platform = platform,
                    video_count = video_ids.len(),
                    error = %e,
                    "Failed to fetch platform videos"
                );
            }
        }

        result
    }

    #[instrument(level = "info", skip(self, user_ids))]
    async fn get_platform_users_by_ids(
        &self,
        user_ids: &[String],
    ) -> Result<Vec<PlatformUser>, Box<dyn Error>> {
        let platform = match self {
            PlatformApiClient::Twitch(_) => "twitch",
            PlatformApiClient::YouTube(_) => "youtube",
        };

        info!(
            platform = platform,
            user_count = user_ids.len(),
            "Fetching platform users by IDs"
        );

        let result = match self {
            PlatformApiClient::Twitch(client) => client.get_platform_users_by_ids(user_ids).await,
            PlatformApiClient::YouTube(client) => client.get_platform_users_by_ids(user_ids).await,
        };

        match &result {
            Ok(users) => {
                info!(
                    platform = platform,
                    requested_count = user_ids.len(),
                    returned_count = users.len(),
                    "Successfully fetched platform users"
                );
            }
            Err(e) => {
                error!(
                    platform = platform,
                    user_count = user_ids.len(),
                    error = %e,
                    "Failed to fetch platform users"
                );
            }
        }

        result
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
