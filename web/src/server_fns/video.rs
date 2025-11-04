//! Server functions for video operations

use crate::server_fns::types::*;
use leptos::prelude::*;

/// Server function to get detailed video information
#[server(GetVideoDetail, "/api")]
pub async fn get_video_detail(id: i32) -> Result<VideoDetailData, ServerFnError> {
    use axum::Extension;
    use leptos_axum::extract;
    use sea_orm::{ColumnTrait, DatabaseConnection, EntityTrait, PaginatorTrait, QueryFilter};
    use std::sync::Arc;
    use yappr_shared::entities::prelude::*;
    use yappr_shared::models::platforms::VideoPlatform;
    use yappr_shared::services::transcription::TranscriptionService;

    let Extension(db) = extract::<Extension<Arc<DatabaseConnection>>>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get DB connection: {}", e)))?;

    // Get video with channel
    let video = Video::find_by_id(id)
        .find_also_related(Channels)
        .one(&*db)
        .await
        .map_err(|e| ServerFnError::new(format!("Database error: {}", e)))?
        .ok_or_else(|| ServerFnError::new("Video not found"))?;

    let (video_model, channel_opt) = video;
    let channel = channel_opt.ok_or_else(|| ServerFnError::new("Channel not found"))?;

    // Get transcriptions for this video
    let transcriptions_models = TranscriptionService::get_by_video_id(&db, id)
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get transcriptions: {}", e)))?;

    // Count segments for this video
    let segment_count = Segments::find()
        .inner_join(Transcriptions)
        .filter(yappr_shared::entities::transcriptions::Column::VideoId.eq(id))
        .count(&*db)
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to count segments: {}", e)))?
        as i32;

    // Check if video has target mappings
    let has_target_mappings = TimestampMapping::find()
        .filter(yappr_shared::entities::timestamp_mapping::Column::TargetVideoId.eq(id))
        .filter(yappr_shared::entities::timestamp_mapping::Column::Active.eq(true))
        .count(&*db)
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to check mappings: {}", e)))?
        > 0;

    // Find source video if there's a mapping
    let source_video_data = if has_target_mappings {
        let mapping = TimestampMapping::find()
            .filter(yappr_shared::entities::timestamp_mapping::Column::TargetVideoId.eq(id))
            .filter(yappr_shared::entities::timestamp_mapping::Column::Active.eq(true))
            .one(&*db)
            .await
            .map_err(|e| ServerFnError::new(format!("Failed to get mapping: {}", e)))?;

        if let Some(mapping_model) = mapping {
            let source_video = Video::find_by_id(mapping_model.source_video_id)
                .find_also_related(Channels)
                .one(&*db)
                .await
                .map_err(|e| ServerFnError::new(format!("Failed to get source video: {}", e)))?;

            if let Some((source_video_model, source_channel_opt)) = source_video {
                if let Some(source_channel) = source_channel_opt {
                    // Recursively get source video transcriptions
                    let source_transcriptions =
                        TranscriptionService::get_by_video_id(&db, source_video_model.id)
                            .await
                            .map_err(|e| {
                                ServerFnError::new(format!(
                                    "Failed to get source transcriptions: {}",
                                    e
                                ))
                            })?;

                    let source_segment_count = Segments::find()
                        .inner_join(Transcriptions)
                        .filter(
                            yappr_shared::entities::transcriptions::Column::VideoId
                                .eq(source_video_model.id),
                        )
                        .count(&*db)
                        .await
                        .map_err(|e| {
                            ServerFnError::new(format!("Failed to count source segments: {}", e))
                        })? as i32;

                    let source_platform_url = if let Some(platform) =
                        VideoPlatform::get_from_str(&source_channel.platform_name)
                    {
                        platform.timestamp_url(&source_video_model.platform_ref, &0)
                    } else {
                        format!("#unknown-platform-{}", source_channel.platform_name)
                    };

                    Some(Box::new(VideoDetailData {
                        id: source_video_model.id,
                        title: source_video_model.title.clone(),
                        uploaded: source_video_model
                            .uploaded
                            .format("%Y-%m-%d %H:%M")
                            .to_string(),
                        duration: source_video_model.duration as i32,
                        active: source_video_model.active,
                        platform_name: source_channel.platform_name.clone(),
                        platform_url: source_platform_url,
                        estimated_upload_time: source_video_model
                            .estimated_upload_time
                            .map(|dt| dt.format("%Y-%m-%d %H:%M").to_string()),
                        channel: ChannelBasicData {
                            id: source_channel.id,
                            name: source_channel.name.clone(),
                            platform_name: source_channel.platform_name.clone(),
                        },
                        source_video: None,
                        has_audio: source_video_model.audio.is_some(),
                        transcriptions: source_transcriptions
                            .into_iter()
                            .map(|t| TranscriptionData {
                                id: t.id,
                                file_extension: t.file_extention.clone(),
                                source_name: format!("{:?}", t.source),
                                last_updated: t.last_updated.format("%Y-%m-%d %H:%M").to_string(),
                                processed: t.processed,
                                segment_count: 0, // Will be populated if needed
                            })
                            .collect(),
                        segment_count: source_segment_count,
                        has_target_mappings: false,
                    }))
                } else {
                    None
                }
            } else {
                None
            }
        } else {
            None
        }
    } else {
        None
    };

    // Generate platform URL
    let platform_url = if let Some(platform) = VideoPlatform::get_from_str(&channel.platform_name) {
        platform.timestamp_url(&video_model.platform_ref, &0)
    } else {
        format!("#unknown-platform-{}", channel.platform_name)
    };

    // Convert transcriptions to DTOs
    let transcriptions = transcriptions_models
        .into_iter()
        .map(|t| TranscriptionData {
            id: t.id,
            file_extension: t.file_extention.clone(),
            source_name: format!("{:?}", t.source),
            last_updated: t.last_updated.format("%Y-%m-%d %H:%M").to_string(),
            processed: t.processed,
            segment_count: 0, // Could count per transcription if needed
        })
        .collect();

    Ok(VideoDetailData {
        id: video_model.id,
        title: video_model.title.clone(),
        uploaded: video_model.uploaded.format("%Y-%m-%d %H:%M").to_string(),
        duration: video_model.duration as i32,
        active: video_model.active,
        platform_name: channel.platform_name.clone(),
        platform_url,
        estimated_upload_time: video_model
            .estimated_upload_time
            .map(|dt| dt.format("%Y-%m-%d %H:%M").to_string()),
        channel: ChannelBasicData {
            id: channel.id,
            name: channel.name.clone(),
            platform_name: channel.platform_name.clone(),
        },
        source_video: source_video_data,
        has_audio: video_model.audio.is_some(),
        transcriptions,
        segment_count,
        has_target_mappings,
    })
}

/// Server function to get transcription segments for a video
#[server(GetTranscriptionSegments, "/api")]
pub async fn get_transcription_segments(
    video_id: i32,
) -> Result<Vec<TranscriptionSegmentData>, ServerFnError> {
    use axum::Extension;
    use leptos_axum::extract;
    use sea_orm::{ColumnTrait, DatabaseConnection, EntityTrait, QueryFilter, QueryOrder};
    use std::sync::Arc;
    use yappr_shared::entities::prelude::*;
    use yappr_shared::models::platforms::VideoPlatform;

    let Extension(db) = extract::<Extension<Arc<DatabaseConnection>>>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get DB connection: {}", e)))?;

    // Get video with channel
    let video = Video::find_by_id(video_id)
        .find_also_related(Channels)
        .one(&*db)
        .await
        .map_err(|e| ServerFnError::new(format!("Database error: {}", e)))?
        .ok_or_else(|| ServerFnError::new("Video not found"))?;

    let (video_model, channel_opt) = video;
    let channel = channel_opt.ok_or_else(|| ServerFnError::new("Channel not found"))?;

    let mut segments_data = Vec::new();

    // Get segments from current video's transcriptions
    let transcriptions = Transcriptions::find()
        .filter(yappr_shared::entities::transcriptions::Column::VideoId.eq(video_id))
        .filter(yappr_shared::entities::transcriptions::Column::Processed.eq(true))
        .all(&*db)
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get transcriptions: {}", e)))?;

    for transcription in transcriptions {
        let segments = Segments::find()
            .filter(yappr_shared::entities::segments::Column::TranscriptionId.eq(transcription.id))
            .order_by_asc(yappr_shared::entities::segments::Column::Start)
            .all(&*db)
            .await
            .map_err(|e| ServerFnError::new(format!("Failed to get segments: {}", e)))?;

        for segment in segments {
            let timestamp_url =
                if let Some(platform) = VideoPlatform::get_from_str(&channel.platform_name) {
                    platform.timestamp_url(&video_model.platform_ref, &(segment.start as u64))
                } else {
                    format!("#unknown-platform-{}", channel.platform_name)
                };

            segments_data.push(TranscriptionSegmentData {
                id: segment.id.to_string(),
                start: segment.start,
                end: segment.end,
                text: segment.text.clone(),
                timestamp_url,
            });
        }
    }

    // Sort by start time
    segments_data.sort_by_key(|s| s.start);

    Ok(segments_data)
}

/// Server function to get chat logs for a video
#[server(GetChatLogs, "/api")]
pub async fn get_chat_logs(video_id: i32) -> Result<Vec<ChatLogData>, ServerFnError> {
    use axum::Extension;
    use leptos_axum::extract;
    use sea_orm::{ColumnTrait, DatabaseConnection, EntityTrait, QueryFilter, QueryOrder};
    use std::sync::Arc;
    use yappr_shared::entities::prelude::*;

    let Extension(db) = extract::<Extension<Arc<DatabaseConnection>>>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get DB connection: {}", e)))?;

    // Get video
    let video = Video::find_by_id(video_id)
        .one(&*db)
        .await
        .map_err(|e| ServerFnError::new(format!("Database error: {}", e)))?
        .ok_or_else(|| ServerFnError::new("Video not found"))?;

    let channel_id = video.channel_id;
    let start_time = video.uploaded;
    let duration_secs = video.duration as i64;
    let end_time = start_time + chrono::Duration::seconds(duration_secs);

    // Get chat logs for this video's time range
    let chat_logs = Chatlogs::find()
        .filter(yappr_shared::entities::chatlogs::Column::ChannelId.eq(channel_id))
        .filter(yappr_shared::entities::chatlogs::Column::Timestamp.gte(start_time))
        .filter(yappr_shared::entities::chatlogs::Column::Timestamp.lte(end_time))
        .order_by_asc(yappr_shared::entities::chatlogs::Column::Timestamp)
        .all(&*db)
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get chat logs: {}", e)))?;

    let chat_data = chat_logs
        .into_iter()
        .map(|log| {
            let offset = (log.timestamp - start_time).num_seconds() as f64;
            ChatLogData {
                id: log.id,
                username: log.username.clone(),
                message: log.message.clone(),
                timestamp: log.timestamp.and_utc().to_rfc3339(),
                offset_seconds: offset,
            }
        })
        .collect();

    Ok(chat_data)
}

/// Server function to fetch video details from platform (admin only)
#[server(FetchVideoDetails, "/api")]
pub async fn fetch_video_details(video_id: i32) -> Result<(), ServerFnError> {
    use axum::Extension;
    use leptos_axum::extract;
    use sea_orm::DatabaseConnection;
    use std::sync::Arc;
    use yappr_shared::services::authorization::AuthContext;

    let Extension(_db) = extract::<Extension<Arc<DatabaseConnection>>>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get DB connection: {}", e)))?;

    let auth_session = extract::<crate::auth::AuthSession>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get auth session: {}", e)))?;

    let auth_context = if let Some(user) = auth_session.user {
        AuthContext::load(&_db, user.0.clone())
            .await
            .map_err(|e| ServerFnError::new(format!("Failed to load auth context: {}", e)))?
    } else {
        return Err(ServerFnError::new("Authentication required"));
    };

    // Require admin or moderator
    if !auth_context.is_admin() && !auth_context.is_moderator() {
        return Err(ServerFnError::new(
            "Permission denied - admin or moderator required",
        ));
    }

    // TODO: Implement actual fetch logic (queue task to fetch details from platform)
    // This would typically queue a background task via Celery or similar

    Ok(())
}

/// Server function to process full video (admin/mod only)
#[server(ProcessFullVideo, "/api")]
pub async fn process_full_video(video_id: i32) -> Result<(), ServerFnError> {
    use axum::Extension;
    use leptos_axum::extract;
    use sea_orm::DatabaseConnection;
    use std::sync::Arc;
    use yappr_shared::services::authorization::AuthContext;

    let Extension(_db) = extract::<Extension<Arc<DatabaseConnection>>>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get DB connection: {}", e)))?;

    let auth_session = extract::<crate::auth::AuthSession>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get auth session: {}", e)))?;

    let auth_context = if let Some(user) = auth_session.user {
        AuthContext::load(&_db, user.0.clone())
            .await
            .map_err(|e| ServerFnError::new(format!("Failed to load auth context: {}", e)))?
    } else {
        return Err(ServerFnError::new("Authentication required"));
    };

    // Require admin or moderator
    if !auth_context.is_admin() && !auth_context.is_moderator() {
        return Err(ServerFnError::new(
            "Permission denied - admin or moderator required",
        ));
    }

    // TODO: Implement queue full processing task
    // This would queue: fetch audio -> transcribe -> process transcriptions

    Ok(())
}
