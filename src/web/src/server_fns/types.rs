//! Data Transfer Objects (DTOs) and type conversions for server functions

use serde::{Deserialize, Serialize};

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

/// Serializable DTO for channel settings
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ChannelSettingsData {
    pub chat_collection_enabled: bool,
    pub content_queue_enabled: bool,
}

/// Serializable DTO for broadcaster settings
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct BroadcasterSettingsData {
    pub linked_discord_channel_id: Option<i64>,
    pub linked_discord_channel_verified: bool,
    pub linked_discord_disable_voting: bool,
    pub linked_discord_threads_enabled: bool,
}

/// Serializable DTO for channel link info
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ChannelLinkData {
    pub id: i32,
    pub name: String,
}

/// Serializable DTO for detailed channel data (used in edit page)
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ChannelDetailData {
    pub id: i32,
    pub name: String,
    pub platform_name: String,
    pub platform_ref: String,
    pub platform_channel_id: String,
    pub main_video_type: String,
    pub last_active: Option<String>,
    pub settings: Option<ChannelSettingsData>,
    pub source_channel: Option<ChannelLinkData>,
}

/// Serializable DTO for broadcaster stats
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct BroadcasterStatsData {
    pub total_channels: usize,
    pub total_videos: i64,
    pub total_transcriptions: i64,
    pub storage_used_gb: f64,
}

/// Serializable DTO for broadcaster edit page data
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct BroadcasterEditData {
    pub broadcaster: BroadcasterData,
    pub channels: Vec<ChannelDetailData>,
    pub settings: Option<BroadcasterSettingsData>,
    pub stats: BroadcasterStatsData,
    pub available_platforms: Vec<String>,
    pub available_video_types: Vec<String>,
}

/// Request DTO for updating broadcaster settings
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct UpdateBroadcasterSettingsRequest {
    pub profile_image_url: Option<String>,
    pub hidden: Option<bool>,
    pub linked_discord_channel_id: Option<i64>,
}

/// Request DTO for updating channel settings
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct UpdateChannelSettingsRequest {
    pub chat_collection_enabled: Option<bool>,
    pub content_queue_enabled: Option<bool>,
    pub main_video_type: Option<String>,
}

/// Request DTO for creating a new channel
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CreateChannelRequest {
    pub name: String,
    pub platform_name: String,
    pub platform_ref: String,
    pub platform_channel_id: String,
    pub main_video_type: String,
}

// ============================================================================
// From implementations for converting database models to DTOs
// ============================================================================

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

#[cfg(feature = "ssr")]
impl From<yappr_shared::entities::channel_settings::Model> for ChannelSettingsData {
    fn from(model: yappr_shared::entities::channel_settings::Model) -> Self {
        Self {
            chat_collection_enabled: model.chat_collection_enabled,
            content_queue_enabled: model.content_queue_enabled,
        }
    }
}

#[cfg(feature = "ssr")]
impl From<yappr_shared::entities::broadcaster_settings::Model> for BroadcasterSettingsData {
    fn from(model: yappr_shared::entities::broadcaster_settings::Model) -> Self {
        Self {
            linked_discord_channel_id: model.linked_discord_channel_id,
            linked_discord_channel_verified: model.linked_discord_channel_verified,
            linked_discord_disable_voting: model.linked_discord_disable_voting,
            linked_discord_threads_enabled: model.linked_discord_threads_enabled,
        }
    }
}
