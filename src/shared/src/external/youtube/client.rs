#[cfg(feature = "youtube")]
use reqwest::Client;
#[cfg(feature = "youtube")]
use serde::Deserialize;
#[cfg(feature = "youtube")]
use std::collections::HashMap;

use crate::{entities::sea_orm_active_enums::Videotype};
use crate::config::Config;
use crate::external::api_client::{ApiClient, PlatformVideo, PlatformUser, PlatformApiClient};
use std::error::Error;
use async_trait::async_trait;

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
    pub async fn new() -> Result<Self, Box<dyn Error>> {
        let config = Config::load();

        let client = Client::builder()
            .user_agent(&config.service_name)
            .build()?;

        Ok(Self {
            client,
            api_key: config.youtube.api_key,
            base_url: "https://www.googleapis.com/youtube/v3".to_string(),
        })
    }

    /// Parse ISO 8601 duration string to std::time::Duration
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
        thumbnails.maxres.as_ref()
            .or(thumbnails.standard.as_ref())
            .or(thumbnails.high.as_ref())
            .or(thumbnails.medium.as_ref())
            .or(thumbnails.default.as_ref())
            .map(|thumb| thumb.url.clone())
    }
}

#[async_trait]
impl ApiClient for YouTubeApiClient {
    async fn get_platform_videos_by_ids(&self, video_ids: &[String]) -> Result<Vec<PlatformVideo>, Box<dyn Error>> {
        if video_ids.is_empty() {
            return Ok(Vec::new());
        }

        let ids_param = video_ids.join(",");
        let mut params = HashMap::new();
        params.insert("key", self.api_key.as_str());
        params.insert("part", "snippet,statistics,contentDetails");
        params.insert("id", &ids_param);

        let url = format!("{}/videos", self.base_url);
        let response = self.client
            .get(&url)
            .query(&params)
            .send()
            .await?;

        if !response.status().is_success() {
            return Err(format!("YouTube API error: {}", response.status()).into());
        }

        let video_response: YouTubeVideoListResponse = response.json().await?;

        let platform_videos: Vec<PlatformVideo> = video_response.items.into_iter().map(|video| {
            let view_count = video.statistics
                .as_ref()
                .and_then(|stats| stats.view_count.as_ref())
                .and_then(|count| count.parse::<u64>().ok());

            let duration = video.content_details
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
        }).collect();

        Ok(platform_videos)
    }

    async fn get_platform_users_by_ids(&self, user_ids: &[String]) -> Result<Vec<PlatformUser>, Box<dyn Error>> {
        if user_ids.is_empty() {
            return Ok(Vec::new());
        }

        let ids_param = user_ids.join(",");
        let mut params = HashMap::new();
        params.insert("key", self.api_key.as_str());
        params.insert("part", "snippet");
        params.insert("id", &ids_param);

        let url = format!("{}/channels", self.base_url);
        let response = self.client
            .get(&url)
            .query(&params)
            .send()
            .await?;

        if !response.status().is_success() {
            return Err(format!("YouTube API error: {}", response.status()).into());
        }

        let channel_response: YouTubeChannelListResponse = response.json().await?;

        let platform_users: Vec<PlatformUser> = channel_response.items.into_iter().map(|channel| {
            PlatformUser {
                id: channel.id,
                display_name: channel.snippet.title,
                profile_image_url: Self::get_best_thumbnail_url(&channel.snippet.thumbnails),
            }
        }).collect();

        Ok(platform_users)
    }
}