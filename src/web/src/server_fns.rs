//! Server functions for interacting with the database
use leptos::prelude::*;
use serde::{Deserialize, Serialize};

#[cfg(feature = "ssr")]
use yappr_shared::services::{
    broadcaster::BroadcasterService,
    channel::ChannelService,
    search::SearchService,
};

/// Serializable DTO for channel data
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ChannelData {
    pub id: i32,
    pub name: String,
    pub platform_name: String,
    pub platform_ref: String,
    pub platform_channel_id: String,
    pub broadcaster_id: i32,
}

/// Serializable DTO for broadcaster data
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct BroadcasterData {
    pub id: i32,
    pub name: String,
    pub hidden: bool,
    pub profile_image_url: Option<String>,
}

/// Serializable DTO for video data
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct VideoData {
    pub id: i32,
    pub title: String,
    pub platform_ref: String,
    pub platform_name: String,
    pub uploaded: i64,  // Unix timestamp
    pub duration: f64,
    pub active: bool,
}

/// Serializable DTO for segment data
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SegmentData {
    pub id: i32,
    pub text: String,
    pub start: i32,
    pub end: i32,
}

/// Serializable DTO for search segment result
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SegmentResultData {
    pub segments: Vec<SegmentData>,
    pub video: VideoData,
    pub search_words: Vec<String>,
    pub formatted_text: String,
    pub start_time: i32,
    pub end_time: i32,
    pub url: String,  // Pre-generated URL for this segment
}

/// Serializable DTO for video search result
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct VideoResultData {
    pub segment_results: Vec<SegmentResultData>,
    pub video: VideoData,
}

#[cfg(feature = "ssr")]
impl From<yappr_shared::entities::channels::Model> for ChannelData {
    fn from(model: yappr_shared::entities::channels::Model) -> Self {
        Self {
            id: model.id,
            name: model.name,
            platform_name: model.platform_name,
            platform_ref: model.platform_ref,
            platform_channel_id: model.platform_channel_id,
            broadcaster_id: model.broadcaster_id,
        }
    }
}

#[cfg(feature = "ssr")]
impl From<yappr_shared::entities::broadcaster::Model> for BroadcasterData {
    fn from(model: yappr_shared::entities::broadcaster::Model) -> Self {
        Self {
            id: model.id,
            name: model.name,
            hidden: model.hidden,
            profile_image_url: model.profile_image_url,
        }
    }
}

#[cfg(feature = "ssr")]
impl VideoData {
    pub fn from_model_with_channel(
        model: yappr_shared::entities::video::Model,
        channel_map: &std::collections::HashMap<i32, yappr_shared::entities::channels::Model>,
    ) -> Result<Self, sea_orm::DbErr> {
        // Use HashMap lookup instead of database query
        let channel = channel_map
            .get(&model.channel_id)
            .ok_or(sea_orm::DbErr::RecordNotFound(format!(
                "Channel {} not found in map",
                model.channel_id
            )))?;

        Ok(Self {
            id: model.id,
            title: model.title,
            platform_ref: model.platform_ref,
            platform_name: channel.platform_name.clone(),
            uploaded: model.uploaded.and_utc().timestamp(),
            duration: model.duration,
            active: model.active,
        })
    }
}

#[cfg(feature = "ssr")]
impl From<yappr_shared::entities::segments::Model> for SegmentData {
    fn from(model: yappr_shared::entities::segments::Model) -> Self {
        Self {
            id: model.id,
            text: model.text,
            start: model.start,
            end: model.end,
        }
    }
}

#[cfg(feature = "ssr")]
impl SegmentResultData {
    pub fn from_model(
        result: yappr_shared::models::search::SegmentsResult,
        channel_map: &std::collections::HashMap<i32, yappr_shared::entities::channels::Model>,
    ) -> Result<Self, sea_orm::DbErr> {
        use yappr_shared::models::platforms::VideoPlatform;

        let start_time = result.start_time();
        let end_time = result.end_time();
        let formatted_text = result.get_sentences_formatted();
        let video_data = VideoData::from_model_with_channel(result.video.clone(), channel_map)?;

        // Generate URL using platform infrastructure
        let url = if let Some(platform) = VideoPlatform::get_from_str(&video_data.platform_name) {
            platform.timestamp_url(&video_data.platform_ref, &(start_time as u64))
        } else {
            format!("#unknown-platform-{}", video_data.platform_name)
        };

        Ok(Self {
            segments: result.segments.into_iter().map(SegmentData::from).collect(),
            video: video_data,
            search_words: result.search_words,
            formatted_text,
            start_time,
            end_time,
            url,
        })
    }
}

#[cfg(feature = "ssr")]
impl VideoResultData {
    pub fn from_model(
        result: yappr_shared::models::search::VideoResult,
        channel_map: &std::collections::HashMap<i32, yappr_shared::entities::channels::Model>,
    ) -> Result<Self, sea_orm::DbErr> {
        let video_data = VideoData::from_model_with_channel(result.video, channel_map)?;

        let mut segment_results = Vec::new();
        for seg_result in result.segment_results {
            segment_results.push(SegmentResultData::from_model(seg_result, channel_map)?);
        }

        Ok(Self {
            segment_results,
            video: video_data,
        })
    }
}

/// Server function to get all channels from the database
#[server(GetChannels, "/api")]
pub async fn get_channels() -> Result<Vec<ChannelData>, ServerFnError> {
    use axum::Extension;
    use leptos_axum::extract;
    use sea_orm::DatabaseConnection;
    use std::sync::Arc;

    // Extract the database connection from Axum Extension
    let Extension(db) = extract::<Extension<Arc<DatabaseConnection>>>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get DB connection: {}", e)))?;

    // Use the ChannelService to fetch all channels
    let channels = ChannelService::get_all_channels(&db)
        .await
        .map_err(|e| ServerFnError::new(format!("Database error: {}", e)))?;

    // Convert to serializable DTOs
    Ok(channels.into_iter().map(ChannelData::from).collect())
}

/// Server function to get channels by platform
#[server(GetChannelsByPlatform, "/api")]
pub async fn get_channels_by_platform(
    platform: String,
) -> Result<Vec<ChannelData>, ServerFnError> {
    use axum::Extension;
    use leptos_axum::extract;
    use sea_orm::DatabaseConnection;
    use std::sync::Arc;

    let Extension(db) = extract::<Extension<Arc<DatabaseConnection>>>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get DB connection: {}", e)))?;

    let channels = ChannelService::get_channels_by_platform(&db, &platform)
        .await
        .map_err(|e| ServerFnError::new(format!("Database error: {}", e)))?;

    Ok(channels.into_iter().map(ChannelData::from).collect())
}

/// Server function to get broadcasters
#[server(GetBroadcasters, "/api")]
pub async fn get_broadcasters(show_hidden: bool) -> Result<Vec<BroadcasterData>, ServerFnError> {
    use axum::Extension;
    use leptos_axum::extract;
    use sea_orm::DatabaseConnection;
    use std::sync::Arc;

    let Extension(db) = extract::<Extension<Arc<DatabaseConnection>>>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get DB connection: {}", e)))?;

    let broadcasters = if show_hidden {
        BroadcasterService::get_all(&db).await
    } else {
        BroadcasterService::get_visible(&db).await
    }
    .map_err(|e| ServerFnError::new(format!("Database error: {}", e)))?;

    Ok(broadcasters.into_iter().map(BroadcasterData::from).collect())
}

/// Server function to search videos
#[server(SearchVideos, "/api")]
pub async fn search_videos(
    search_term: String,
    broadcaster_id: i32,
    start_date: Option<String>,
    end_date: Option<String>,
    channel_type: String,
) -> Result<Vec<VideoResultData>, ServerFnError> {
    use axum::Extension;
    use leptos_axum::extract;
    use sea_orm::DatabaseConnection;
    use std::sync::Arc;
    use yappr_shared::chrono::{DateTime, NaiveDate, Utc};

    let Extension(db) = extract::<Extension<Arc<DatabaseConnection>>>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get DB connection: {}", e)))?;

    // Get channels for the broadcaster
    let all_channels = ChannelService::get_channels_by_broadcaster(&db, broadcaster_id)
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get channels: {}", e)))?;

    // Filter channels by type
    let channels: Vec<_> = all_channels
        .into_iter()
        .filter(|channel| {
            channel_type == "all"
                || channel.platform_name.to_lowercase() == channel_type.to_lowercase()
        })
        .collect();

    if channels.is_empty() {
        return Ok(Vec::new());
    }

    let channel_ids: Vec<i32> = channels.iter().map(|c| c.id).collect();

    // Parse date strings to DateTime<Utc>
    let start_date_parsed: Option<DateTime<Utc>> = start_date.and_then(|s| {
        NaiveDate::parse_from_str(&s, "%Y-%m-%d")
            .ok()
            .map(|d| d.and_hms_opt(0, 0, 0).unwrap().and_utc())
    });

    let end_date_parsed: Option<DateTime<Utc>> = end_date.and_then(|s| {
        NaiveDate::parse_from_str(&s, "%Y-%m-%d")
            .ok()
            .map(|d| d.and_hms_opt(23, 59, 59).unwrap().and_utc())
    });

    // Perform search
    let results = SearchService::search(
        &db,
        &search_term,
        channel_ids,
        start_date_parsed,
        end_date_parsed,
    )
    .await
    .map_err(|e| ServerFnError::new(format!("Search error: {}", e)))?;

    if results.is_empty() {
        return Ok(Vec::new());
    }

    // Batch load all channels needed for conversion (eliminates N+1 query problem)
    use std::collections::{HashMap, HashSet};
    use sea_orm::{ColumnTrait, EntityTrait, QueryFilter};
    use yappr_shared::entities::prelude::*;

    let channel_ids_needed: Vec<i32> = results
        .iter()
        .map(|r| r.video.channel_id)
        .collect::<HashSet<_>>()
        .into_iter()
        .collect();

    let channels = Channels::find()
        .filter(yappr_shared::entities::channels::Column::Id.is_in(channel_ids_needed))
        .all(&*db)
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to load channels: {}", e)))?;

    let channel_map: HashMap<i32, _> = channels
        .into_iter()
        .map(|c| (c.id, c))
        .collect();

    // Convert to DTOs using channel map (no more database queries!)
    let mut video_results = Vec::new();
    for result in results {
        match VideoResultData::from_model(result, &channel_map) {
            Ok(vr) => video_results.push(vr),
            Err(e) => return Err(ServerFnError::new(format!("Conversion error: {}", e))),
        }
    }

    Ok(video_results)
}
