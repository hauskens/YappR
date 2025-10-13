#[cfg(feature = "twitch")]
use twitch_api::{
    helix::{
        users::GetUsersRequest,
        videos::GetVideosRequest,
    },
    types::{UserId, VideoId},
    HelixClient,
};
#[cfg(feature = "twitch")]
use twitch_oauth2::AppAccessToken;
#[cfg(feature = "database")]
use crate::{entities::sea_orm_active_enums::Videotype};
use crate::config::Config;
use crate::external::api_client::{ApiClient, PlatformVideo, PlatformUser, PlatformApiClient};
use std::error::Error;
use async_trait::async_trait;

/// Twitch API client wrapper with different authentication contexts
pub struct TwitchApiClient {
    client: HelixClient<'static, reqwest::Client>,
    token: AppAccessToken,
}

#[cfg(feature = "twitch")]
impl TwitchApiClient {

    /// Create a client authenticated as the server/bot user
    pub async fn new() -> Result<Self, Box<dyn Error>> {

        let config = Config::load();

        let client: HelixClient<reqwest::Client> = twitch_api::HelixClient::default();
        let token = twitch_oauth2::AppAccessToken::get_app_access_token(
            &client,
            config.twitch.client_id,
            config.twitch.client_secret,
            vec![],
        ).await?;
        let client = HelixClient::with_client(
            twitch_api::client::ClientDefault::default_client_with_name(
                Some(config.service_name.parse()?)
            )?
        );
        
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
    async fn get_platform_videos_by_ids(&self, video_ids: &[String]) -> Result<Vec<PlatformVideo>, Box<dyn Error>> {
        let ids: Vec<VideoId> = video_ids.iter().map(|id| VideoId::new(id.clone())).collect();
        let request = GetVideosRequest::ids(ids.as_slice());
        let response = self.client.req_get(request, &self.token).await?;
        
        Ok(response.data.into_iter().map(|video| PlatformVideo {
            id: video.id.to_string(),
            title: video.title.clone(),
            duration: None,
            created_at: video.created_at.to_string().parse().unwrap(),
            thumbnail_url: Some(video.thumbnail_url.clone()),
            view_count: Some(video.view_count as u64),
            video_type: Videotype::Vod,
        }).collect())
    }

    async fn get_platform_users_by_ids(&self, user_ids: &[String]) -> Result<Vec<PlatformUser>, Box<dyn Error>> {
        let ids: Vec<UserId> = user_ids.iter().map(|id| UserId::new(id.clone())).collect();
        
        let request = GetUsersRequest::ids(ids.as_slice());
        let response = self.client.req_get(request, &self.token).await?;
        
        Ok(response.data.into_iter().map(|user| PlatformUser {
            id: user.id.to_string(),
            display_name: user.display_name.to_string(),
            profile_image_url: user.profile_image_url,
        }).collect())
    }

}