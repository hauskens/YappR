use crate::config::Config;
#[cfg(feature = "database")]
use crate::entities::sea_orm_active_enums::Videotype;
use crate::external::api_client::{ApiClient, PlatformUser, PlatformVideo};
use async_trait::async_trait;
use std::error::Error;
use tracing::{debug, error, info, instrument};
#[cfg(feature = "twitch")]
use twitch_api::{
    HelixClient,
    helix::{users::GetUsersRequest, videos::GetVideosRequest},
    types::{UserId, VideoId},
};
#[cfg(feature = "twitch")]
use twitch_oauth2::AppAccessToken;

#[cfg(feature = "twitch")]
use reqwest;

/// Twitch API client wrapper with different authentication contexts
pub struct TwitchApiClient {
    client: HelixClient<'static, reqwest::Client>,
    token: AppAccessToken,
}

#[cfg(feature = "twitch")]
impl TwitchApiClient {
    /// Create a client authenticated as the server/bot user
    #[instrument(level = "info")]
    pub async fn new() -> Result<Self, Box<dyn Error>> {
        info!("Initializing Twitch API client");

        let config = Config::load();

        debug!("Creating Twitch Helix client");
        let client: HelixClient<reqwest::Client> = twitch_api::HelixClient::default();

        info!("Obtaining Twitch app access token");
        let token = match twitch_oauth2::AppAccessToken::get_app_access_token(
            &client,
            config.twitch.client_id.clone(),
            config.twitch.client_secret.clone(),
            vec![],
        )
        .await
        {
            Ok(token) => {
                info!("Successfully obtained Twitch app access token");
                token
            }
            Err(e) => {
                error!(error = %e, "Failed to obtain Twitch app access token");
                return Err(e.into());
            }
        };

        let client =
            HelixClient::with_client(twitch_api::client::ClientDefault::default_client_with_name(
                Some(config.service_name.parse()?),
            )?);
        let client = {
            debug!("Twitch Helix client configured successfully");
            client
        };

        info!("Twitch API client initialized successfully");
        Ok(Self { client, token })
    }

    // /// Get Twitch user by username
    // pub async fn get_user_by_login(&self, username: &str) -> Result<twitch_api::helix::users::User> {
    //     let logins = vec![username];
    //     let request = GetUsersRequest::logins(&logins);
    //     let response = self.client.req_get(request, &self.token).await?;

    //     response.data.into_iter().next()
    //         .ok_or_else(|| eyre!("User not found: {}", username))
    // }

    // /// Get Twitch user by ID
    // pub async fn get_user_by_id(&self, user_id: &str) -> Result<twitch_api::helix::users::User> {
    //     let ids = vec![UserId::new(user_id.to_string())];
    //     let request = GetUsersRequest::ids(ids.as_slice());
    //     let response = self.client.req_get(request, &self.token).await?;

    //     response.data.into_iter().next()
    //         .ok_or_else(|| eyre!("User not found: {}", user_id))
    // }

    // /// Get multiple Twitch users by IDs
    // pub async fn get_users_by_ids(&self, user_ids: &[String]) -> Result<Vec<twitch_api::helix::users::User>> {
    //     let ids: Vec<UserId> = user_ids.iter().map(|id| UserId::new(id.clone())).collect();
    //     let request = GetUsersRequest::ids(ids.as_slice());
    //     let response = self.client.req_get(request, &self.token).await?;

    //     Ok(response.data)
    // }

    // /// Get current live streams for user IDs
    // pub async fn get_current_live_streams(&self, user_ids: &[String]) -> Result<Vec<twitch_api::helix::streams::Stream>> {
    //     let ids: Vec<UserId> = user_ids.iter().map(|id| UserId::new(id.clone())).collect();
    //     let request = GetStreamsRequest::user_ids(ids.as_slice());
    //     let response = self.client.req_get(request, &self.token).await?;

    //     Ok(response.data)
    // }

    // /// Get latest broadcasts (archived videos) for a user
    // pub async fn get_latest_broadcasts(&self, user_id: &str, _limit: Option<usize>) -> Result<Vec<twitch_api::helix::videos::Video>> {
    //     let request = GetVideosRequest::user_id(UserId::new(user_id.to_string()));

    //     let response = self.client.req_get(request, &self.token).await?;
    //     Ok(response.data)
    // }

    // /// Get clips by IDs
    // pub async fn get_clips(&self, clip_ids: &[String]) -> Result<Vec<twitch_api::helix::clips::Clip>> {
    //     let ids: Vec<ClipId> = clip_ids.iter().map(|id| ClipId::new(id.clone())).collect();
    //     let request = GetClipsRequest::clip_ids(ids.as_slice());
    //     let response = self.client.req_get(request, &self.token).await?;

    //     Ok(response.data)
    // }

    // /// Get moderators for a channel (requires broadcaster_id)
    // pub async fn get_channel_moderators(&self, broadcaster_id: &str) -> Result<Vec<twitch_api::helix::moderation::Moderator>> {
    //     let request = GetModeratorsRequest::broadcaster_id(UserId::new(broadcaster_id.to_string()));
    //     let response = self.client.req_get(request, &self.token).await?;

    //     Ok(response.data)
    // }

    // pub async fn get_platform_video_by_ids(&self, video_ids: &[String]) -> Result<Vec<PlatformVideo>> {
    //     let videos = self.get_videos_by_ids(video_ids).await?;
    //     Ok(videos.into_iter().map(|video| TwitchApiClient::convert_video(&video)).collect())
    // }
}

#[async_trait]
impl ApiClient for TwitchApiClient {
    #[instrument(level = "info", skip(self, video_ids))]
    async fn get_platform_videos_by_ids(
        &self,
        video_ids: &[String],
    ) -> Result<Vec<PlatformVideo>, Box<dyn Error>> {
        info!(
            video_count = video_ids.len(),
            "Fetching Twitch videos by IDs"
        );

        let ids: Vec<VideoId> = video_ids
            .iter()
            .map(|id| VideoId::new(id.clone()))
            .collect();
        let request = GetVideosRequest::ids(ids.as_slice());

        debug!("Making Twitch API request for videos");
        let response = match self.client.req_get(request, &self.token).await {
            Ok(response) => {
                debug!(
                    returned_count = response.data.len(),
                    "Twitch API videos request successful"
                );
                response
            }
            Err(e) => {
                error!(error = %e, video_count = video_ids.len(), "Twitch API videos request failed");
                return Err(e.into());
            }
        };

        let videos: Vec<PlatformVideo> = response
            .data
            .into_iter()
            .map(|video| PlatformVideo {
                id: video.id.to_string(),
                title: video.title.clone(),
                duration: None,
                created_at: video.created_at.to_string().parse().unwrap(),
                thumbnail_url: Some(video.thumbnail_url.clone()),
                view_count: Some(video.view_count as u64),
                video_type: Videotype::Vod,
            })
            .collect();

        info!(
            requested_count = video_ids.len(),
            returned_count = videos.len(),
            "Successfully processed Twitch videos"
        );

        Ok(videos)
    }

    #[instrument(level = "info", skip(self, user_ids))]
    async fn get_platform_users_by_ids(
        &self,
        user_ids: &[String],
    ) -> Result<Vec<PlatformUser>, Box<dyn Error>> {
        info!(user_count = user_ids.len(), "Fetching Twitch users by IDs");

        let ids: Vec<UserId> = user_ids.iter().map(|id| UserId::new(id.clone())).collect();
        let request = GetUsersRequest::ids(ids.as_slice());

        debug!("Making Twitch API request for users");
        let response = match self.client.req_get(request, &self.token).await {
            Ok(response) => {
                debug!(
                    returned_count = response.data.len(),
                    "Twitch API users request successful"
                );
                response
            }
            Err(e) => {
                error!(error = %e, user_count = user_ids.len(), "Twitch API users request failed");
                return Err(e.into());
            }
        };

        let users: Vec<PlatformUser> = response
            .data
            .into_iter()
            .map(|user| PlatformUser {
                id: user.id.to_string(),
                display_name: user.display_name.to_string(),
                profile_image_url: user.profile_image_url,
            })
            .collect();

        info!(
            requested_count = user_ids.len(),
            returned_count = users.len(),
            "Successfully processed Twitch users"
        );

        Ok(users)
    }
}
