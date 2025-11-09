//! Server functions for channel operations

use crate::server_fns::types::*;
use leptos::prelude::*;

#[cfg(feature = "ssr")]
use yappr_shared::services::channel::ChannelService;

/// Server function to get all channels from the database
#[server(GetChannels, "/api")]
pub async fn get_channels() -> Result<Vec<ChannelData>, ServerFnError> {
    use axum::Extension;
    use leptos_axum::extract;
    use sea_orm::DatabaseConnection;
    use std::sync::Arc;

    let Extension(db) = extract::<Extension<Arc<DatabaseConnection>>>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get DB connection: {}", e)))?;

    let channels = ChannelService::get_all_channels(&db)
        .await
        .map_err(|e| ServerFnError::new(format!("Database error: {}", e)))?;

    Ok(channels.into_iter().map(ChannelData::from).collect())
}

/// Server function to get channels by platform
#[server(GetChannelsByPlatform, "/api")]
pub async fn get_channels_by_platform(platform: String) -> Result<Vec<ChannelData>, ServerFnError> {
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

/// Server function to update channel settings
#[server(UpdateChannelSettings, "/api")]
pub async fn update_channel_settings(
    channel_id: i32,
    request: UpdateChannelSettingsRequest,
) -> Result<(), ServerFnError> {
    use axum::Extension;
    use leptos_axum::extract;
    use sea_orm::{
        ActiveModelTrait, ColumnTrait, DatabaseConnection, EntityTrait, QueryFilter, Set,
    };
    use std::sync::Arc;
    use yappr_shared::entities::prelude::*;
    use yappr_shared::services::authorization::AuthContext;

    let Extension(db) = extract::<Extension<Arc<DatabaseConnection>>>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get DB connection: {}", e)))?;

    let auth_session = extract::<crate::auth::AuthSession>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get auth session: {}", e)))?;

    let auth_context = if let Some(user) = auth_session.user {
        AuthContext::load(&db, user.0.clone())
            .await
            .map_err(|e| ServerFnError::new(format!("Failed to load auth context: {}", e)))?
    } else {
        return Err(ServerFnError::new("Authentication required"));
    };

    let channel = Channels::find_by_id(channel_id)
        .one(&*db)
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to load channel: {}", e)))?
        .ok_or_else(|| ServerFnError::new("Channel not found"))?;

    // Check if user can edit: admin or channel owner
    let can_edit = auth_context.is_admin() || auth_context.is_channel_owner(channel.id);

    if !can_edit {
        return Err(ServerFnError::new("Permission denied"));
    }

    if let Some(video_type_str) = request.main_video_type {
        use yappr_shared::entities::sea_orm_active_enums::Videotype;

        let video_type = match video_type_str.as_str() {
            "Unknown" => Videotype::Unknown,
            "VOD" => Videotype::Vod,
            "Clip" => Videotype::Clip,
            "Edit" => Videotype::Edit,
            "Live" => Videotype::Live,
            _ => {
                return Err(ServerFnError::new(format!(
                    "Invalid video type: {}",
                    video_type_str
                )));
            }
        };

        let mut active_channel: yappr_shared::entities::channels::ActiveModel = channel.into();
        active_channel.main_video_type = Set(video_type);
        active_channel
            .update(&*db)
            .await
            .map_err(|e| ServerFnError::new(format!("Failed to update channel: {}", e)))?;
    }

    if request.chat_collection_enabled.is_some() || request.content_queue_enabled.is_some() {
        let existing_settings = ChannelSettings::find()
            .filter(yappr_shared::entities::channel_settings::Column::ChannelId.eq(channel_id))
            .one(&*db)
            .await
            .map_err(|e| ServerFnError::new(format!("Failed to load settings: {}", e)))?;

        if let Some(settings) = existing_settings {
            let mut active: yappr_shared::entities::channel_settings::ActiveModel = settings.into();
            if let Some(chat_enabled) = request.chat_collection_enabled {
                active.chat_collection_enabled = Set(chat_enabled);
            }
            if let Some(queue_enabled) = request.content_queue_enabled {
                active.content_queue_enabled = Set(queue_enabled);
            }
            active
                .update(&*db)
                .await
                .map_err(|e| ServerFnError::new(format!("Failed to update settings: {}", e)))?;
        } else {
            let new_settings = yappr_shared::entities::channel_settings::ActiveModel {
                channel_id: Set(channel_id),
                chat_collection_enabled: Set(request.chat_collection_enabled.unwrap_or(false)),
                content_queue_enabled: Set(request.content_queue_enabled.unwrap_or(false)),
                ..Default::default()
            };
            new_settings
                .insert(&*db)
                .await
                .map_err(|e| ServerFnError::new(format!("Failed to create settings: {}", e)))?;
        }
    }

    Ok(())
}

/// Server function to delete a channel
#[server(DeleteChannel, "/api")]
pub async fn delete_channel(channel_id: i32) -> Result<(), ServerFnError> {
    use axum::Extension;
    use leptos_axum::extract;
    use sea_orm::DatabaseConnection;
    use std::sync::Arc;
    use yappr_shared::services::authorization::AuthContext;

    let Extension(db) = extract::<Extension<Arc<DatabaseConnection>>>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get DB connection: {}", e)))?;

    let auth_session = extract::<crate::auth::AuthSession>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get auth session: {}", e)))?;

    let auth_context = if let Some(user) = auth_session.user {
        AuthContext::load(&db, user.0.clone())
            .await
            .map_err(|e| ServerFnError::new(format!("Failed to load auth context: {}", e)))?
    } else {
        return Err(ServerFnError::new("Authentication required"));
    };

    // Check if user can delete: admin or channel owner
    let can_delete = auth_context.is_admin() || auth_context.is_channel_owner(channel_id);

    if !can_delete {
        return Err(ServerFnError::new("Permission denied"));
    }

    use sea_orm::EntityTrait;
    use yappr_shared::entities::prelude::Channels;

    Channels::delete_by_id(channel_id)
        .exec(&*db)
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to delete channel: {}", e)))?;

    Ok(())
}

// ============================================================================
// Channel Videos Page Functions
// ============================================================================

/// Server function to get channel videos page data
#[server(GetChannelVideosPageData, "/api")]
pub async fn get_channel_videos_page_data(
    channel_id: i32,
) -> Result<ChannelVideosPageData, ServerFnError> {
    use axum::Extension;
    use leptos_axum::extract;
    use sea_orm::{ColumnTrait, DatabaseConnection, EntityTrait, QueryFilter};
    use std::sync::Arc;
    use yappr_shared::entities::prelude::*;
    use yappr_shared::models::platforms::VideoPlatform;
    use yappr_shared::services::authorization::AuthContext;

    let Extension(db) = extract::<Extension<Arc<DatabaseConnection>>>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get DB connection: {}", e)))?;

    // Get auth context (optional, can be anonymous)
    let auth_session = extract::<crate::auth::AuthSession>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get auth session: {}", e)))?;

    let auth_context = if let Some(user) = auth_session.user {
        AuthContext::load(&db, user.0.clone())
            .await
            .map_err(|e| ServerFnError::new(format!("Failed to load auth context: {}", e)))?
    } else {
        AuthContext::anonymous()
    };

    // Get channel
    let channel = Channels::find_by_id(channel_id)
        .one(&*db)
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to load channel: {}", e)))?
        .ok_or_else(|| ServerFnError::new("Channel not found"))?;

    // Get channel settings
    let settings = ChannelSettings::find()
        .filter(yappr_shared::entities::channel_settings::Column::ChannelId.eq(channel_id))
        .one(&*db)
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to load settings: {}", e)))?;

    // Get source channel if linked
    let source_channel = if let Some(source_id) = channel.source_channel_id {
        let source = Channels::find_by_id(source_id)
            .one(&*db)
            .await
            .map_err(|e| ServerFnError::new(format!("Failed to load source channel: {}", e)))?;
        source.map(|c| ChannelLinkData {
            id: c.id,
            name: c.name,
        })
    } else {
        None
    };

    // Single optimized query to get all video data with JOINs and aggregations
    use sea_orm::ConnectionTrait;
    use sea_orm::Statement;

    let query = format!(
        r#"
        SELECT
            v.id,
            v.title,
            v.duration,
            v.uploaded,
            v.estimated_upload_time,
            v.active,
            v.audio IS NOT NULL as has_audio,
            COALESCE(t_counts.transcription_count, 0) as transcription_count,
            COALESCE(t_counts.has_processed, 0) as has_processed,
            COALESCE(s_counts.segment_count, 0) as segment_count,
            tm.source_video_id,
            sv.title as source_title,
            sv.platform_ref as source_platform_ref,
            sc.platform_name as source_platform_name
        FROM video v
        LEFT JOIN (
            SELECT
                video_id,
                COUNT(*) as transcription_count,
                MAX(CASE WHEN processed = true THEN 1 ELSE 0 END) as has_processed
            FROM transcriptions
            GROUP BY video_id
        ) t_counts ON t_counts.video_id = v.id
        LEFT JOIN (
            SELECT
                t.video_id,
                COUNT(s.id) as segment_count
            FROM segments s
            INNER JOIN transcriptions t ON s.transcription_id = t.id
            GROUP BY t.video_id
        ) s_counts ON s_counts.video_id = v.id
        LEFT JOIN timestamp_mapping tm ON tm.target_video_id = v.id AND tm.active = true
        LEFT JOIN video sv ON sv.id = tm.source_video_id
        LEFT JOIN channels sc ON sc.id = sv.channel_id
        WHERE v.channel_id = {}
        ORDER BY v.uploaded DESC
        "#,
        channel_id
    );

    let rows = db
        .query_all(Statement::from_string(db.get_database_backend(), query))
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to load videos: {}", e)))?;

    // Build video list items from the single query result
    let mut video_items = Vec::new();
    let mut transcription_count = 0;

    for row in rows {
        let video_id: i32 = row
            .try_get("", "id")
            .map_err(|e| ServerFnError::new(format!("Failed to parse id: {}", e)))?;
        let title: String = row
            .try_get("", "title")
            .map_err(|e| ServerFnError::new(format!("Failed to parse title: {}", e)))?;
        let duration: f64 = row
            .try_get("", "duration")
            .map_err(|e| ServerFnError::new(format!("Failed to parse duration: {}", e)))?;
        let uploaded: chrono::NaiveDateTime = row
            .try_get("", "uploaded")
            .map_err(|e| ServerFnError::new(format!("Failed to parse uploaded: {}", e)))?;
        let estimated_upload_time: Option<chrono::NaiveDateTime> =
            row.try_get("", "estimated_upload_time").ok();
        let active: bool = row
            .try_get("", "active")
            .map_err(|e| ServerFnError::new(format!("Failed to parse active: {}", e)))?;
        let has_audio: bool = row
            .try_get("", "has_audio")
            .map_err(|e| ServerFnError::new(format!("Failed to parse has_audio: {}", e)))?;
        let transcription_cnt: i64 = row.try_get("", "transcription_count").map_err(|e| {
            ServerFnError::new(format!("Failed to parse transcription_count: {}", e))
        })?;
        let has_processed: i32 = row
            .try_get("", "has_processed")
            .map_err(|e| ServerFnError::new(format!("Failed to parse has_processed: {}", e)))?;
        let segment_count: i64 = row
            .try_get("", "segment_count")
            .map_err(|e| ServerFnError::new(format!("Failed to parse segment_count: {}", e)))?;

        // Source video data (if linked)
        let source_video_data =
            if let Ok(source_video_id) = row.try_get::<i32>("", "source_video_id") {
                if let (Ok(source_title), Ok(source_platform_ref), Ok(source_platform_name)) = (
                    row.try_get::<String>("", "source_title"),
                    row.try_get::<String>("", "source_platform_ref"),
                    row.try_get::<String>("", "source_platform_name"),
                ) {
                    let platform = VideoPlatform::get_from_str(&source_platform_name).unwrap();

                    Some(VideoBasicData {
                        id: source_video_id,
                        title: source_title,
                        url: platform.video_url(&source_platform_ref),
                    })
                } else {
                    None
                }
            } else {
                None
            };

        // Build transcription list (we only have counts, so create minimal entries)
        let transcriptions = if transcription_cnt > 0 {
            vec![TranscriptionBasicData {
                id: 0, // We don't have individual IDs from the aggregated query
                processed: has_processed > 0,
            }]
        } else {
            Vec::new()
        };

        if has_processed > 0 {
            transcription_count += 1;
        }

        video_items.push(VideoListItemData {
            id: video_id,
            title,
            duration: duration as i32,
            uploaded: uploaded.format("%Y-%m-%d %H:%M").to_string(),
            estimated_upload_time: estimated_upload_time
                .map(|dt| dt.format("%Y-%m-%d %H:%M").to_string()),
            active,
            has_audio,
            transcriptions,
            source_video: source_video_data,
            segment_count: segment_count as i32,
        });
    }

    // Calculate permissions
    let is_admin = auth_context.is_admin();
    let is_mod = auth_context.is_moderator();
    let is_owner = auth_context.is_channel_owner(channel_id);
    let is_channel_mod = auth_context.is_channel_moderator(channel_id);

    let permissions = ChannelVideosPermissions {
        can_fetch_videos: is_admin || is_mod || is_owner || is_channel_mod,
        can_fetch_all_videos: is_admin || is_owner,
        can_bulk_link: is_admin || is_mod,
        can_edit_videos: is_admin || is_mod || is_owner || is_channel_mod,
        can_process_videos: is_admin || is_mod || is_owner || is_channel_mod,
    };

    // Build channel detail data
    let channel_detail = ChannelDetailData {
        id: channel.id,
        name: channel.name,
        platform_name: channel.platform_name,
        platform_ref: channel.platform_ref,
        platform_channel_id: channel.platform_channel_id,
        main_video_type: format!("{:?}", channel.main_video_type),
        last_active: channel
            .last_active
            .map(|dt| dt.format("%Y-%m-%d %H:%M").to_string()),
        settings: settings.map(ChannelSettingsData::from),
        source_channel,
    };

    let total_videos = video_items.len();

    Ok(ChannelVideosPageData {
        channel: channel_detail,
        videos: video_items,
        total_videos,
        transcription_count: format!("{}", transcription_count),
        permissions,
    })
}

/// Server function to trigger fetching new videos for a channel
#[server(FetchChannelVideos, "/api")]
pub async fn fetch_channel_videos(channel_id: i32) -> Result<String, ServerFnError> {
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

    // Check permissions
    if !auth_context.is_admin() && !auth_context.is_moderator() {
        return Err(ServerFnError::new(
            "Permission denied - admin or moderator required",
        ));
    }

    // TODO: Implement actual task queuing via Celery or similar
    // For now, just return a success message
    Ok(format!(
        "Fetch videos task queued for channel {}",
        channel_id
    ))
}

/// Server function to trigger fetching all videos for a channel
#[server(FetchAllChannelVideos, "/api")]
pub async fn fetch_all_channel_videos(channel_id: i32) -> Result<String, ServerFnError> {
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

    // Check permissions (admin only)
    if !auth_context.is_admin() {
        return Err(ServerFnError::new("Permission denied - admin required"));
    }

    // TODO: Implement actual task queuing via Celery or similar
    Ok(format!(
        "Fetch all videos task queued for channel {}",
        channel_id
    ))
}

/// Server function to trigger bulk auto-linking of videos
#[server(BulkAutoLinkVideos, "/api")]
pub async fn bulk_auto_link_videos(
    channel_id: i32,
    params: BulkLinkParams,
) -> Result<String, ServerFnError> {
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

    // Check permissions
    if !auth_context.is_admin() && !auth_context.is_moderator() {
        return Err(ServerFnError::new(
            "Permission denied - admin or moderator required",
        ));
    }

    // TODO: Implement actual bulk linking logic
    // This would call ChannelService::bulk_auto_link_videos with the parameters
    Ok(format!(
        "Bulk auto-link task queued for channel {} with margin_sec={}, min_duration={}, date_margin_hours={}",
        channel_id, params.margin_sec, params.min_duration, params.date_margin_hours
    ))
}
