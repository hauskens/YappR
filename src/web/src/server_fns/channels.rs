//! Server functions for channel operations

use leptos::prelude::*;
use crate::server_fns::types::*;

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

/// Server function to update channel settings
#[server(UpdateChannelSettings, "/api")]
pub async fn update_channel_settings(
    channel_id: i32,
    request: UpdateChannelSettingsRequest,
) -> Result<(), ServerFnError> {
    use axum::Extension;
    use leptos_axum::extract;
    use sea_orm::{DatabaseConnection, EntityTrait, ActiveModelTrait, Set, QueryFilter, ColumnTrait};
    use std::sync::Arc;
    use yappr_shared::services::authorization::AuthContext;
    use yappr_shared::entities::prelude::*;

    let Extension(db) = extract::<Extension<Arc<DatabaseConnection>>>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get DB connection: {}", e)))?;

    let auth_session = extract::<crate::auth::AuthSession>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get auth session: {}", e)))?;

    let auth_context = if let Some(user) = auth_session.user {
        AuthContext::load(&db, user.0.clone()).await
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
    let can_edit = auth_context.is_admin()
        || auth_context.is_channel_owner(channel.id);

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
            _ => return Err(ServerFnError::new(format!("Invalid video type: {}", video_type_str))),
        };

        let mut active_channel: yappr_shared::entities::channels::ActiveModel = channel.into();
        active_channel.main_video_type = Set(video_type);
        active_channel.update(&*db).await
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
            active.update(&*db).await
                .map_err(|e| ServerFnError::new(format!("Failed to update settings: {}", e)))?;
        } else {
            let new_settings = yappr_shared::entities::channel_settings::ActiveModel {
                channel_id: Set(channel_id),
                chat_collection_enabled: Set(request.chat_collection_enabled.unwrap_or(false)),
                content_queue_enabled: Set(request.content_queue_enabled.unwrap_or(false)),
                ..Default::default()
            };
            new_settings.insert(&*db).await
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
        AuthContext::load(&db, user.0.clone()).await
            .map_err(|e| ServerFnError::new(format!("Failed to load auth context: {}", e)))?
    } else {
        return Err(ServerFnError::new("Authentication required"));
    };

    // Check if user can delete: admin or channel owner
    let can_delete = auth_context.is_admin()
        || auth_context.is_channel_owner(channel_id);

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
