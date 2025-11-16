#[cfg(feature = "youtube")]
use reqwest::Client;
#[cfg(feature = "youtube")]
use serde::Deserialize;
#[cfg(feature = "youtube")]
use std::collections::HashMap;

use crate::config::Config;
use crate::entities::sea_orm_active_enums::Videotype;
use crate::external::api_client::{ApiClient, PlatformUser, PlatformVideo};
use async_trait::async_trait;
use std::error::Error;
use tracing::{debug, error, info, instrument, warn};

/// YouTube API client wrapper using reqwest
pub struct YouTubeApiClient {
    client: Client,
    api_key: String,
    base_url: String,
}

#[cfg(feature = "youtube")]
#[derive(Debug, Deserialize)]
struct YouTubeVideoListResponse {
    items: Vec<YouTubeVideo>,
}

#[cfg(feature = "youtube")]
#[derive(Debug, Deserialize)]
struct YouTubeVideo {
    id: String,
    snippet: YouTubeVideoSnippet,
    statistics: Option<YouTubeVideoStatistics>,
    #[serde(rename = "contentDetails")]
    content_details: Option<YouTubeContentDetails>,
}

#[cfg(feature = "youtube")]
#[derive(Debug, Deserialize)]
struct YouTubeVideoSnippet {
    title: String,
    #[serde(rename = "publishedAt")]
    published_at: String,
    thumbnails: YouTubeThumbnails,
    #[serde(rename = "channelId")]
    _channel_id: String,
    #[serde(rename = "channelTitle")]
    _channel_title: String,
}

#[cfg(feature = "youtube")]
#[derive(Debug, Deserialize)]
struct YouTubeVideoStatistics {
    #[serde(rename = "viewCount")]
    view_count: Option<String>,
}

#[cfg(feature = "youtube")]
#[derive(Debug, Deserialize)]
struct YouTubeContentDetails {
    duration: Option<String>,
}

#[cfg(feature = "youtube")]
#[derive(Debug, Deserialize)]
struct YouTubeThumbnails {
    default: Option<YouTubeThumbnail>,
    medium: Option<YouTubeThumbnail>,
    high: Option<YouTubeThumbnail>,
    standard: Option<YouTubeThumbnail>,
    maxres: Option<YouTubeThumbnail>,
}

#[cfg(feature = "youtube")]
#[derive(Debug, Deserialize)]
struct YouTubeThumbnail {
    url: String,
}

#[cfg(feature = "youtube")]
#[derive(Debug, Deserialize)]
struct YouTubeChannelListResponse {
    items: Vec<YouTubeChannel>,
}

#[cfg(feature = "youtube")]
#[derive(Debug, Deserialize)]
struct YouTubeChannel {
    id: String,
    snippet: YouTubeChannelSnippet,
}

#[cfg(feature = "youtube")]
#[derive(Debug, Deserialize)]
struct YouTubeChannelSnippet {
    title: String,
    thumbnails: YouTubeThumbnails,
}

#[cfg(feature = "youtube")]
impl YouTubeApiClient {
    /// Create a new YouTube API client
    #[instrument(level = "info")]
    pub async fn new() -> Result<Self, Box<dyn Error>> {
        info!("Initializing YouTube API client");
        let config = Config::load();

        debug!("Creating HTTP client for YouTube API");
        let client = match Client::builder()
            .user_agent(config.service_name.to_string())
            .build()
        {
            Ok(client) => {
                debug!("YouTube HTTP client created successfully");
                client
            }
            Err(e) => {
                error!(error = %e, "Failed to create YouTube HTTP client");
                return Err(e.into());
            }
        };

        info!("YouTube API client initialized successfully");
        Ok(Self {
            client,
            api_key: config.youtube.api_key.value.clone(),
            base_url: "https://www.googleapis.com/youtube/v3".to_string(),
        })
    }

    /// Parse ISO 8601 duration string to std::time::Duration
    #[instrument(level = "debug")]
    fn parse_duration(duration_str: &str) -> Option<std::time::Duration> {
        // YouTube returns durations in ISO 8601 format like "PT4M13S" or "PT1H2M3S"
        if !duration_str.starts_with("PT") {
            return None;
        }

        let duration_str = &duration_str[2..]; // Remove "PT" prefix
        let mut total_seconds = 0u64;
        let mut current_number = String::new();

        for ch in duration_str.chars() {
            if ch.is_ascii_digit() {
                current_number.push(ch);
            } else {
                if let Ok(num) = current_number.parse::<u64>() {
                    match ch {
                        'H' => total_seconds += num * 3600,
                        'M' => total_seconds += num * 60,
                        'S' => total_seconds += num,
                        _ => {}
                    }
                }
                current_number.clear();
            }
        }

        Some(std::time::Duration::from_secs(total_seconds))
    }

    /// Get the best available thumbnail URL
    fn get_best_thumbnail_url(thumbnails: &YouTubeThumbnails) -> Option<String> {
        thumbnails
            .maxres
            .as_ref()
            .or(thumbnails.standard.as_ref())
            .or(thumbnails.high.as_ref())
            .or(thumbnails.medium.as_ref())
            .or(thumbnails.default.as_ref())
            .map(|thumb| thumb.url.clone())
    }
}

#[async_trait]
impl ApiClient for YouTubeApiClient {
    #[instrument(level = "info", skip(self, video_ids))]
    async fn get_platform_videos_by_ids(
        &self,
        video_ids: &[String],
    ) -> Result<Vec<PlatformVideo>, Box<dyn Error>> {
        info!(
            video_count = video_ids.len(),
            "Fetching YouTube videos by IDs"
        );

        if video_ids.is_empty() {
            debug!("No video IDs provided, returning empty result");
            return Ok(Vec::new());
        }

        let ids_param = video_ids.join(",");
        let mut params = HashMap::new();
        params.insert("key", self.api_key.as_str());
        params.insert("part", "snippet,statistics,contentDetails");
        params.insert("id", &ids_param);

        let url = format!("{}/videos", self.base_url);
        debug!(url = %url, params = ?params, "Making YouTube API request for videos");

        let response = match self.client.get(&url).query(&params).send().await {
            Ok(response) => {
                debug!(status = %response.status(), "YouTube API response received");
                response
            }
            Err(e) => {
                error!(error = %e, video_count = video_ids.len(), "YouTube API request failed");
                return Err(e.into());
            }
        };

        if !response.status().is_success() {
            error!(status = %response.status(), video_count = video_ids.len(), "YouTube API returned error status");
            return Err(format!("YouTube API error: {}", response.status()).into());
        }

        let video_response: YouTubeVideoListResponse =
            match response.json::<YouTubeVideoListResponse>().await {
                Ok(parsed) => {
                    debug!(
                        returned_count = parsed.items.len(),
                        "YouTube API response parsed successfully"
                    );
                    parsed
                }
                Err(e) => {
                    error!(error = %e, "Failed to parse YouTube API response");
                    return Err(e.into());
                }
            };

        let platform_videos: Vec<PlatformVideo> = video_response
            .items
            .into_iter()
            .map(|video| {
                let view_count = video
                    .statistics
                    .as_ref()
                    .and_then(|stats| stats.view_count.as_ref())
                    .and_then(|count| count.parse::<u64>().ok());

                let duration = video
                    .content_details
                    .as_ref()
                    .and_then(|details| details.duration.as_ref())
                    .and_then(|dur| Self::parse_duration(dur));

                let created_at = chrono::DateTime::parse_from_rfc3339(&video.snippet.published_at)
                    .map(|dt| dt.with_timezone(&chrono::Utc))
                    .unwrap_or_else(|_| chrono::Utc::now());

                PlatformVideo {
                    id: video.id,
                    title: video.snippet.title,
                    duration,
                    created_at,
                    thumbnail_url: Self::get_best_thumbnail_url(&video.snippet.thumbnails),
                    view_count,
                    video_type: Videotype::Vod,
                }
            })
            .collect();

        info!(
            requested_count = video_ids.len(),
            returned_count = platform_videos.len(),
            "Successfully processed YouTube videos"
        );

        Ok(platform_videos)
    }

    #[instrument(level = "info", skip(self, user_ids))]
    async fn get_platform_users_by_ids(
        &self,
        user_ids: &[String],
    ) -> Result<Vec<PlatformUser>, Box<dyn Error>> {
        info!(user_count = user_ids.len(), "Fetching YouTube users by IDs");

        if user_ids.is_empty() {
            debug!("No user IDs provided, returning empty result");
            return Ok(Vec::new());
        }

        let ids_param = user_ids.join(",");
        let mut params = HashMap::new();
        params.insert("key", self.api_key.as_str());
        params.insert("part", "snippet");
        params.insert("id", &ids_param);

        let url = format!("{}/channels", self.base_url);
        debug!(url = %url, "Making YouTube API request for channels");

        let response = match self.client.get(&url).query(&params).send().await {
            Ok(response) => {
                debug!(status = %response.status(), "YouTube API response received");
                response
            }
            Err(e) => {
                error!(error = %e, user_count = user_ids.len(), "YouTube API request failed");
                return Err(e.into());
            }
        };

        if !response.status().is_success() {
            error!(status = %response.status(), user_count = user_ids.len(), "YouTube API returned error status");
            return Err(format!("YouTube API error: {}", response.status()).into());
        }

        let channel_response: YouTubeChannelListResponse =
            match response.json::<YouTubeChannelListResponse>().await {
                Ok(parsed) => {
                    debug!(
                        returned_count = parsed.items.len(),
                        "YouTube API response parsed successfully"
                    );
                    parsed
                }
                Err(e) => {
                    error!(error = %e, "Failed to parse YouTube API response");
                    return Err(e.into());
                }
            };

        let platform_users: Vec<PlatformUser> = channel_response
            .items
            .into_iter()
            .map(|channel| PlatformUser {
                id: channel.id,
                display_name: channel.snippet.title,
                profile_image_url: Self::get_best_thumbnail_url(&channel.snippet.thumbnails),
            })
            .collect();

        info!(
            requested_count = user_ids.len(),
            returned_count = platform_users.len(),
            "Successfully processed YouTube users"
        );

        Ok(platform_users)
    }
}
