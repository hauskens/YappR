//! Server functions for broadcaster operations

use leptos::prelude::*;
use crate::server_fns::types::*;

#[cfg(feature = "ssr")]
use yappr_shared::services::broadcaster::BroadcasterService;

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

/// Server function to get broadcasters with authentication and permission filtering
#[server(GetBroadcastersWithAuth, "/api")]
pub async fn get_broadcasters_with_auth() -> Result<Vec<BroadcasterData>, ServerFnError> {
    use axum::Extension;
    use leptos_axum::extract;
    use sea_orm::{DatabaseConnection, EntityTrait, ColumnTrait, QueryFilter};
    use std::sync::Arc;
    use std::collections::HashSet;
    use yappr_shared::services::authorization::AuthContext;
    use yappr_shared::services::moderation::ModerationService;
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
        AuthContext::anonymous()
    };

    let all_broadcasters = if auth_context.is_admin() || auth_context.is_moderator() {
        BroadcasterService::get_all(&db).await
    } else {
        BroadcasterService::get_visible(&db).await
    }
    .map_err(|e| ServerFnError::new(format!("Database error: {}", e)))?;

    let banned_broadcaster_ids: HashSet<i32> = if let Some(user) = auth_context.user.as_ref() {
        let actions = ModerationService::get_active_actions_for_user(&db, user.id)
            .await
            .map_err(|e| ServerFnError::new(format!("Failed to get moderation actions: {}", e)))?;

        let banned_channel_ids: Vec<i32> = actions
            .into_iter()
            .filter_map(|action| action.channel_id)
            .collect();

        if !banned_channel_ids.is_empty() {
            let channels = Channels::find()
                .filter(yappr_shared::entities::channels::Column::Id.is_in(banned_channel_ids))
                .all(&*db)
                .await
                .map_err(|e| ServerFnError::new(format!("Failed to load channels: {}", e)))?;

            channels.into_iter().map(|ch| ch.broadcaster_id).collect()
        } else {
            HashSet::new()
        }
    } else {
        HashSet::new()
    };

    let filtered_broadcasters: Vec<BroadcasterData> = all_broadcasters
        .into_iter()
        .filter(|b| !banned_broadcaster_ids.contains(&b.id))
        .map(BroadcasterData::from)
        .collect();

    Ok(filtered_broadcasters)
}

/// Server function to get complete broadcaster edit data with authorization
#[server(GetBroadcasterEditData, "/api")]
pub async fn get_broadcaster_edit_data(
    broadcaster_id: i32,
) -> Result<BroadcasterEditData, ServerFnError> {
    use axum::Extension;
    use leptos_axum::extract;
    use sea_orm::{DatabaseConnection, EntityTrait, ColumnTrait, QueryFilter, PaginatorTrait};
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
        AuthContext::anonymous()
    };

    let broadcaster = Broadcaster::find_by_id(broadcaster_id)
        .one(&*db)
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to load broadcaster: {}", e)))?
        .ok_or_else(|| ServerFnError::new("Broadcaster not found"))?;

    // Check if user can view broadcaster: admin, moderator, or has channel role
    let mut can_view = auth_context.is_admin() || auth_context.is_moderator();

    if !can_view {
        // Check if user owns or moderates any channel for this broadcaster
        let broadcaster_channels = Channels::find()
            .filter(yappr_shared::entities::channels::Column::BroadcasterId.eq(broadcaster_id))
            .all(&*db)
            .await
            .map_err(|e| ServerFnError::new(format!("Failed to load channels: {}", e)))?;

        can_view = broadcaster_channels.iter().any(|ch| {
            auth_context.is_channel_owner(ch.id) || auth_context.is_channel_moderator(ch.id)
        });
    }

    if !can_view && broadcaster.hidden {
        return Err(ServerFnError::new("Broadcaster not found or access denied"));
    }

    let all_channels = Channels::find()
        .filter(yappr_shared::entities::channels::Column::BroadcasterId.eq(broadcaster_id))
        .all(&*db)
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to load channels: {}", e)))?;

    let channel_ids: Vec<i32> = all_channels.iter().map(|c| c.id).collect();
    let channel_settings = if !channel_ids.is_empty() {
        ChannelSettings::find()
            .filter(yappr_shared::entities::channel_settings::Column::ChannelId.is_in(channel_ids.clone()))
            .all(&*db)
            .await
            .map_err(|e| ServerFnError::new(format!("Failed to load channel settings: {}", e)))?
    } else {
        vec![]
    };

    let settings_map: std::collections::HashMap<i32, yappr_shared::entities::channel_settings::Model> =
        channel_settings.into_iter().map(|s| (s.channel_id, s)).collect();

    let mut channel_details = Vec::new();
    for channel in all_channels.iter() {
        let settings = settings_map.get(&channel.id).map(|s| ChannelSettingsData {
            chat_collection_enabled: s.chat_collection_enabled,
            content_queue_enabled: s.content_queue_enabled,
        });

        let source_channel = if let Some(source_id) = channel.source_channel_id {
            Channels::find_by_id(source_id)
                .one(&*db)
                .await
                .ok()
                .flatten()
                .map(|sc| ChannelLinkData {
                    id: sc.id,
                    name: sc.name,
                })
        } else {
            None
        };

        let last_active = channel.last_active.map(|dt| dt.format("%Y-%m-%d %H:%M:%S").to_string());

        // Convert Videotype enum to string
        let video_type_str = match channel.main_video_type {
            yappr_shared::entities::sea_orm_active_enums::Videotype::Unknown => "Unknown",
            yappr_shared::entities::sea_orm_active_enums::Videotype::Vod => "VOD",
            yappr_shared::entities::sea_orm_active_enums::Videotype::Clip => "Clip",
            yappr_shared::entities::sea_orm_active_enums::Videotype::Edit => "Edit",
            yappr_shared::entities::sea_orm_active_enums::Videotype::Live => "Live",
        }.to_string();

        channel_details.push(ChannelDetailData {
            id: channel.id,
            name: channel.name.clone(),
            platform_name: channel.platform_name.clone(),
            platform_ref: channel.platform_ref.clone(),
            platform_channel_id: channel.platform_channel_id.clone(),
            main_video_type: video_type_str,
            last_active,
            settings,
            source_channel,
        });
    }

    let broadcaster_settings = BroadcasterSettings::find()
        .filter(yappr_shared::entities::broadcaster_settings::Column::BroadcasterId.eq(broadcaster_id))
        .one(&*db)
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to load broadcaster settings: {}", e)))?
        .map(BroadcasterSettingsData::from);

    let total_channels = all_channels.len();

    let total_videos: i64 = if !channel_ids.is_empty() {
        let count = Video::find()
            .filter(yappr_shared::entities::video::Column::ChannelId.is_in(channel_ids.clone()))
            .filter(yappr_shared::entities::video::Column::Active.eq(true))
            .count(&*db)
            .await
            .map_err(|e| ServerFnError::new(format!("Failed to count videos: {}", e)))?;
        count as i64
    } else {
        0
    };

    let total_transcriptions: i64 = if !channel_ids.is_empty() {
        let count = Video::find()
            .inner_join(Transcriptions)
            .filter(yappr_shared::entities::video::Column::ChannelId.is_in(channel_ids))
            .filter(yappr_shared::entities::video::Column::Active.eq(true))
            .count(&*db)
            .await
            .map_err(|e| ServerFnError::new(format!("Failed to count transcriptions: {}", e)))?;
        count as i64
    } else {
        0
    };

    let storage_used_gb = 0.0;

    let stats = BroadcasterStatsData {
        total_channels,
        total_videos,
        total_transcriptions,
        storage_used_gb,
    };

    let available_platforms = vec!["Twitch".to_string(), "YouTube".to_string()];
    let available_video_types = vec!["Live".to_string(), "VOD".to_string(), "Clip".to_string()];

    Ok(BroadcasterEditData {
        broadcaster: BroadcasterData::from(broadcaster),
        channels: channel_details,
        settings: broadcaster_settings,
        stats,
        available_platforms,
        available_video_types,
    })
}

/// Server function to update broadcaster settings
#[server(UpdateBroadcasterSettings, "/api")]
pub async fn update_broadcaster_settings(
    broadcaster_id: i32,
    request: UpdateBroadcasterSettingsRequest,
) -> Result<(), ServerFnError> {
    use axum::Extension;
    use leptos_axum::extract;
    use sea_orm::{DatabaseConnection, EntityTrait, ActiveModelTrait, Set, ColumnTrait, QueryFilter};
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

    // Check if user can edit: admin or owns any channel for this broadcaster
    let mut can_edit = auth_context.is_admin();

    if !can_edit {
        let broadcaster_channels = Channels::find()
            .filter(yappr_shared::entities::channels::Column::BroadcasterId.eq(broadcaster_id))
            .all(&*db)
            .await
            .map_err(|e| ServerFnError::new(format!("Failed to load channels: {}", e)))?;

        can_edit = broadcaster_channels.iter().any(|ch| auth_context.is_channel_owner(ch.id));
    }

    if !can_edit {
        return Err(ServerFnError::new("Permission denied"));
    }

    if request.profile_image_url.is_some() || request.hidden.is_some() {
        let broadcaster = Broadcaster::find_by_id(broadcaster_id)
            .one(&*db)
            .await
            .map_err(|e| ServerFnError::new(format!("Failed to load broadcaster: {}", e)))?
            .ok_or_else(|| ServerFnError::new("Broadcaster not found"))?;

        let mut active_model: yappr_shared::entities::broadcaster::ActiveModel = broadcaster.into();

        if let Some(url) = request.profile_image_url {
            active_model.profile_image_url = Set(if url.is_empty() { None } else { Some(url) });
        }

        if let Some(hidden) = request.hidden {
            active_model.hidden = Set(hidden);
        }

        active_model.update(&*db).await
            .map_err(|e| ServerFnError::new(format!("Failed to update broadcaster: {}", e)))?;
    }

    if let Some(discord_id) = request.linked_discord_channel_id {
        let existing_settings = BroadcasterSettings::find()
            .filter(yappr_shared::entities::broadcaster_settings::Column::BroadcasterId.eq(broadcaster_id))
            .one(&*db)
            .await
            .map_err(|e| ServerFnError::new(format!("Failed to load settings: {}", e)))?;

        if let Some(settings) = existing_settings {
            let mut active: yappr_shared::entities::broadcaster_settings::ActiveModel = settings.into();
            active.linked_discord_channel_id = Set(Some(discord_id));
            active.update(&*db).await
                .map_err(|e| ServerFnError::new(format!("Failed to update settings: {}", e)))?;
        } else {
            let new_settings = yappr_shared::entities::broadcaster_settings::ActiveModel {
                broadcaster_id: Set(broadcaster_id),
                linked_discord_channel_id: Set(Some(discord_id)),
                ..Default::default()
            };
            new_settings.insert(&*db).await
                .map_err(|e| ServerFnError::new(format!("Failed to create settings: {}", e)))?;
        }
    }

    Ok(())
}

/// Server function to delete a broadcaster
#[server(DeleteBroadcaster, "/api")]
pub async fn delete_broadcaster(broadcaster_id: i32) -> Result<(), ServerFnError> {
    use axum::Extension;
    use leptos_axum::extract;
    use sea_orm::{DatabaseConnection, EntityTrait};
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

    // Only admin can delete broadcasters (destructive operation)
    if !auth_context.is_admin() {
        return Err(ServerFnError::new("Admin permission required"));
    }

    // Delete broadcaster - this will cascade delete related entities
    Broadcaster::delete_by_id(broadcaster_id)
        .exec(&*db)
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to delete broadcaster: {}", e)))?;

    Ok(())
}
