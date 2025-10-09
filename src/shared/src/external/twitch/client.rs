use eyre::{eyre, Context, Result};
#[cfg(feature = "twitch")]
use twitch_api::{
    helix::{
        clips::GetClipsRequest,
        moderation::GetModeratorsRequest,
        streams::GetStreamsRequest,
        users::GetUsersRequest,
        videos::GetVideosRequest,
    },
    types::{UserId, VideoId, ClipId},
    HelixClient,
};
use twitch_oauth2::AppAccessToken;
use crate::{utils};
use crate::external::api_client::{PlatformUser, PlatformVideo};
use super::twitch_auth::get_server_token;

/// Twitch API client wrapper with different authentication contexts
pub struct TwitchApiClient {
    client: HelixClient<'static, reqwest::Client>,
    token: AppAccessToken,
}

#[cfg(feature = "twitch")]
impl TwitchApiClient {
    /// Create a new client with the provided token
    pub fn new(client: HelixClient<'static, reqwest::Client>, token: AppAccessToken) -> Self {
        Self { client, token }
    }

    /// Create a client authenticated as the server/bot user
    pub async fn server_client() -> Result<Self> {
        let token = get_server_token().await
            .context("Failed to get server user token")?;
        
        let client = HelixClient::with_client(
            twitch_api::client::ClientDefault::default_client_with_name(
                Some("yappr_server".parse()?)
            )?
        );
        
        Ok(Self::new(client, token))
    }

    // /// Create a client authenticated for a specific user
    // pub async fn user_client(user_id: i32) -> Result<Self> {
    //     let db = get_database_connection().await?;
    //     let user_service = UserService::new(db);
        
    //     let user = user_service.get_user_by_id(user_id).await?;
        
    //     let oauth_token = user_service.get_user_oauth_token(user.id).await?
    //         .ok_or_else(|| eyre!("No OAuth token found for user"))?;

    //     let client_id = twitch_oauth2::ClientId::new(env::var("TWITCH_CLIENT_ID")?);
    //     let client_secret = twitch_oauth2::ClientSecret::new(env::var("TWITCH_CLIENT_SECRET")?);
    //     let access_token = twitch_oauth2::AccessToken::new(oauth_token.access_token);
    //     let refresh_token = twitch_oauth2::RefreshToken::new(oauth_token.refresh_token);

    //     let client = HelixClient::with_client(
    //         twitch_api::client::ClientDefault::default_client_with_name(
    //             Some("yappr_user".parse()?)
    //         )?
    //     );

    //     let token = UserToken::from_existing_or_refresh_token(
    //         &client,
    //         access_token,
    //         refresh_token,
    //         client_id,
    //         client_secret,
    //     ).await?;

    //     Ok(Self::new(client, token))
    // }

    /// Get Twitch user by username
    pub async fn get_user_by_login(&self, username: &str) -> Result<twitch_api::helix::users::User> {
        let logins = vec![username];
        let request = GetUsersRequest::logins(&logins);
        let response = self.client.req_get(request, &self.token).await?;
        
        response.data.into_iter().next()
            .ok_or_else(|| eyre!("User not found: {}", username))
    }

    /// Get Twitch user by ID
    pub async fn get_user_by_id(&self, user_id: &str) -> Result<twitch_api::helix::users::User> {
        let ids = vec![UserId::new(user_id.to_string())];
        let request = GetUsersRequest::ids(ids.as_slice());
        let response = self.client.req_get(request, &self.token).await?;
        
        response.data.into_iter().next()
            .ok_or_else(|| eyre!("User not found: {}", user_id))
    }

    /// Get multiple Twitch users by IDs
    pub async fn get_users_by_ids(&self, user_ids: &[String]) -> Result<Vec<twitch_api::helix::users::User>> {
        let ids: Vec<UserId> = user_ids.iter().map(|id| UserId::new(id.clone())).collect();
        let request = GetUsersRequest::ids(ids.as_slice());
        let response = self.client.req_get(request, &self.token).await?;
        
        Ok(response.data)
    }

    /// Get current live streams for user IDs
    pub async fn get_current_live_streams(&self, user_ids: &[String]) -> Result<Vec<twitch_api::helix::streams::Stream>> {
        let ids: Vec<UserId> = user_ids.iter().map(|id| UserId::new(id.clone())).collect();
        let request = GetStreamsRequest::user_ids(ids.as_slice());
        let response = self.client.req_get(request, &self.token).await?;
        
        Ok(response.data)
    }

    /// Get latest broadcasts (archived videos) for a user
    pub async fn get_latest_broadcasts(&self, user_id: &str, _limit: Option<usize>) -> Result<Vec<twitch_api::helix::videos::Video>> {
        let request = GetVideosRequest::user_id(UserId::new(user_id.to_string()));

        let response = self.client.req_get(request, &self.token).await?;
        Ok(response.data)
    }

    /// Get videos by IDs
    pub async fn get_videos_by_ids(&self, video_ids: &[String]) -> Result<Vec<twitch_api::helix::videos::Video>> {
        let ids: Vec<VideoId> = video_ids.iter().map(|id| VideoId::new(id.clone())).collect();
        let request = GetVideosRequest::ids(ids.as_slice());
        let response = self.client.req_get(request, &self.token).await?;
        
        Ok(response.data)
    }

    /// Get clips by IDs
    pub async fn get_clips(&self, clip_ids: &[String]) -> Result<Vec<twitch_api::helix::clips::Clip>> {
        let ids: Vec<ClipId> = clip_ids.iter().map(|id| ClipId::new(id.clone())).collect();
        let request = GetClipsRequest::clip_ids(ids.as_slice());
        let response = self.client.req_get(request, &self.token).await?;
        
        Ok(response.data)
    }

    /// Get moderators for a channel (requires broadcaster_id)
    pub async fn get_channel_moderators(&self, broadcaster_id: &str) -> Result<Vec<twitch_api::helix::moderation::Moderator>> {
        let request = GetModeratorsRequest::broadcaster_id(UserId::new(broadcaster_id.to_string()));
        let response = self.client.req_get(request, &self.token).await?;
        
        Ok(response.data)
    }

    pub async fn get_platform_video_by_ids(&self, video_ids: &[String]) -> Result<Vec<PlatformVideo>> {
        let videos = self.get_videos_by_ids(video_ids).await?;
        Ok(videos.into_iter().map(|video| TwitchApiClient::convert_video(&video)).collect())
    }

}

// Helper functions to convert Twitch API types to platform-agnostic types
impl TwitchApiClient {
    pub fn convert_user(user: twitch_api::helix::users::User) -> PlatformUser {
        PlatformUser {
            id: user.id.to_string(),
            display_name: user.display_name.to_string(),
            profile_image_url: user.profile_image_url,
        }
    }

    pub fn convert_video(video: &twitch_api::helix::videos::Video) -> PlatformVideo {
        PlatformVideo {
            id: video.id.clone().to_string(),
            title: video.title.clone(),
            created_at: video.created_at.clone().as_str().parse().expect("Failed to parse timestamp"),
            thumbnail_url: Some(video.thumbnail_url.clone()),
            duration: Some(utils::parse_duration(&video.duration.clone()).unwrap()),
            view_count: Some(video.view_count.clone() as u64),
            video_type: match video.type_ {
                twitch_api::types::VideoType::Archive => crate::entities::sea_orm_active_enums::Videotype::Vod,
                twitch_api::types::VideoType::Highlight => crate::entities::sea_orm_active_enums::Videotype::Edit,
                twitch_api::types::VideoType::Upload => crate::entities::sea_orm_active_enums::Videotype::Edit,
                _ => crate::entities::sea_orm_active_enums::Videotype::Unknown,
            },
        }
    }

}

