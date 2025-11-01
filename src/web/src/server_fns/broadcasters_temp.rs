// This file contains server functions specific to broadcaster edit page
// It's separated due to size and will be included in server_fns.rs

/// Server function to get complete broadcaster edit data with authorization
#[server(GetBroadcasterEditData, "/api")]
pub async fn get_broadcaster_edit_data(
    broadcaster_id: i32,
) -> Result<BroadcasterEditData, ServerFnError> {
    use axum::Extension;
    use leptos_axum::extract;
    use sea_orm::{DatabaseConnection, EntityTrait, ColumnTrait, QueryFilter, QuerySelect};
    use std::sync::Arc;
    use yappr_shared::services::authorization::{AuthContext, ChannelRole};
    use yappr_shared::entities::prelude::*;

    let Extension(db) = extract::<Extension<Arc<DatabaseConnection>>>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get DB connection: {}", e)))?;

    // Extract auth session
    let auth_session = extract::<crate::auth::AuthSession>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get auth session: {}", e)))?;

    // Load authorization context
    let auth_context = if let Some(user) = auth_session.user {
        AuthContext::load(&db, user.0.clone()).await
            .map_err(|e| ServerFnError::new(format!("Failed to load auth context: {}", e)))?
    } else {
        AuthContext::anonymous()
    };

    // Load broadcaster
    let broadcaster = Broadcaster::find_by_id(broadcaster_id)
        .one(&*db)
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to load broadcaster: {}", e)))?
        .ok_or_else(|| ServerFnError::new("Broadcaster not found"))?;

    // Check permission to view this broadcaster
    let can_view = auth_context.is_admin()
        || auth_context.is_moderator()
        || auth_context.user.as_ref().map(|u| u.broadcaster_ids.contains(&broadcaster_id)).unwrap_or(false)
        || auth_context.has_channel_role_for_broadcaster(broadcaster_id, &ChannelRole::Mod);

    if !can_view && broadcaster.hidden {
        return Err(ServerFnError::new("Broadcaster not found or access denied"));
    }

    // Load all channels for this broadcaster
    let all_channels = Channels::find()
        .filter(yappr_shared::entities::channels::Column::BroadcasterId.eq(broadcaster_id))
        .all(&*db)
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to load channels: {}", e)))?;

    // Load settings for all channels (batch query)
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

    // Create a map of channel_id -> settings
    let settings_map: std::collections::HashMap<i32, yappr_shared::entities::channel_settings::Model> =
        channel_settings.into_iter().map(|s| (s.channel_id, s)).collect();

    // Build channel detail data
    let mut channel_details = Vec::new();
    for channel in all_channels.iter() {
        let settings = settings_map.get(&channel.id).map(|s| ChannelSettingsData {
            chat_collection_enabled: s.chat_collection_enabled,
            content_queue_enabled: s.content_queue_enabled,
        });

        // Load source channel if linked
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

        channel_details.push(ChannelDetailData {
            id: channel.id,
            name: channel.name.clone(),
            platform_name: channel.platform_name.clone(),
            platform_ref: channel.platform_ref.clone(),
            platform_channel_id: channel.platform_channel_id.clone(),
            main_video_type: channel.main_video_type.clone(),
            last_active,
            settings,
            source_channel,
        });
    }

    // Load broadcaster settings
    let broadcaster_settings = BroadcasterSettings::find()
        .filter(yappr_shared::entities::broadcaster_settings::Column::BroadcasterId.eq(broadcaster_id))
        .one(&*db)
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to load broadcaster settings: {}", e)))?
        .map(BroadcasterSettingsData::from);

    // Calculate stats
    let total_channels = all_channels.len();

    // Count total videos across all channels
    let total_videos: i64 = if !channel_ids.is_empty() {
        Video::find()
            .filter(yappr_shared::entities::video::Column::ChannelId.is_in(channel_ids.clone()))
            .filter(yappr_shared::entities::video::Column::Active.eq(true))
            .count(&*db)
            .await
            .map_err(|e| ServerFnError::new(format!("Failed to count videos: {}", e)))?
    } else {
        0
    };

    // Count total transcriptions
    let total_transcriptions: i64 = if !channel_ids.is_empty() {
        use sea_orm::JoinType;

        Video::find()
            .join(JoinType::InnerJoin, yappr_shared::entities::video::Relation::Transcription.def())
            .filter(yappr_shared::entities::video::Column::ChannelId.is_in(channel_ids))
            .filter(yappr_shared::entities::video::Column::Active.eq(true))
            .count(&*db)
            .await
            .map_err(|e| ServerFnError::new(format!("Failed to count transcriptions: {}", e)))?
    } else {
        0
    };

    // For storage, we'd need to calculate from file sizes - for now use placeholder
    let storage_used_gb = 0.0;

    let stats = BroadcasterStatsData {
        total_channels,
        total_videos,
        total_transcriptions,
        storage_used_gb,
    };

    // Get available platforms and video types
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
    use sea_orm::{DatabaseConnection, EntityTrait, ActiveModelTrait, Set};
    use std::sync::Arc;
    use yappr_shared::services::authorization::AuthContext;
    use yappr_shared::entities::prelude::*;

    let Extension(db) = extract::<Extension<Arc<DatabaseConnection>>>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get DB connection: {}", e)))?;

    // Extract and check auth
    let auth_session = extract::<crate::auth::AuthSession>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get auth session: {}", e)))?;

    let auth_context = if let Some(user) = auth_session.user {
        AuthContext::load(&db, user.0.clone()).await
            .map_err(|e| ServerFnError::new(format!("Failed to load auth context: {}", e)))?
    } else {
        return Err(ServerFnError::new("Authentication required"));
    };

    // Check permission
    let can_edit = auth_context.is_admin()
        || auth_context.user.as_ref().map(|u| u.broadcaster_ids.contains(&broadcaster_id)).unwrap_or(false);

    if !can_edit {
        return Err(ServerFnError::new("Permission denied"));
    }

    // Update broadcaster model if needed
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

    // Update broadcaster settings if Discord channel ID provided
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

/// Server function to update channel settings
#[server(UpdateChannelSettings, "/api")]
pub async fn update_channel_settings(
    channel_id: i32,
    request: UpdateChannelSettingsRequest,
) -> Result<(), ServerFnError> {
    use axum::Extension;
    use leptos_axum::extract;
    use sea_orm::{DatabaseConnection, EntityTrait, ActiveModelTrait, Set};
    use std::sync::Arc;
    use yappr_shared::services::authorization::AuthContext;
    use yappr_shared::entities::prelude::*;

    let Extension(db) = extract::<Extension<Arc<DatabaseConnection>>>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get DB connection: {}", e)))?;

    // Extract and check auth
    let auth_session = extract::<crate::auth::AuthSession>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get auth session: {}", e)))?;

    let auth_context = if let Some(user) = auth_session.user {
        AuthContext::load(&db, user.0.clone()).await
            .map_err(|e| ServerFnError::new(format!("Failed to load auth context: {}", e)))?
    } else {
        return Err(ServerFnError::new("Authentication required"));
    };

    // Load channel to get broadcaster_id
    let channel = Channels::find_by_id(channel_id)
        .one(&*db)
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to load channel: {}", e)))?
        .ok_or_else(|| ServerFnError::new("Channel not found"))?;

    // Check permission
    let can_edit = auth_context.is_admin()
        || auth_context.user.as_ref().map(|u| u.broadcaster_ids.contains(&channel.broadcaster_id)).unwrap_or(false);

    if !can_edit {
        return Err(ServerFnError::new("Permission denied"));
    }

    // Update channel main_video_type if provided
    if let Some(video_type) = request.main_video_type {
        let mut active_channel: yappr_shared::entities::channels::ActiveModel = channel.into();
        active_channel.main_video_type = Set(video_type);
        active_channel.update(&*db).await
            .map_err(|e| ServerFnError::new(format!("Failed to update channel: {}", e)))?;
    }

    // Update channel settings if provided
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

    // Extract and check auth
    let auth_session = extract::<crate::auth::AuthSession>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get auth session: {}", e)))?;

    let auth_context = if let Some(user) = auth_session.user {
        AuthContext::load(&db, user.0.clone()).await
            .map_err(|e| ServerFnError::new(format!("Failed to load auth context: {}", e)))?
    } else {
        return Err(ServerFnError::new("Authentication required"));
    };

    // Only admins or broadcaster owners can delete
    let can_delete = auth_context.is_admin()
        || auth_context.user.as_ref().map(|u| u.broadcaster_ids.contains(&broadcaster_id)).unwrap_or(false);

    if !can_delete {
        return Err(ServerFnError::new("Permission denied"));
    }

    // Use BroadcasterService to delete (handles cascading)
    use yappr_shared::services::broadcaster::BroadcasterService;
    BroadcasterService::delete(&db, broadcaster_id).await
        .map_err(|e| ServerFnError::new(format!("Failed to delete broadcaster: {}", e)))?;

    Ok(())
}

/// Server function to delete a channel
#[server(DeleteChannel, "/api")]
pub async fn delete_channel(channel_id: i32) -> Result<(), ServerFnError> {
    use axum::Extension;
    use leptos_axum::extract;
    use sea_orm::{DatabaseConnection, EntityTrait};
    use std::sync::Arc;
    use yappr_shared::services::authorization::AuthContext;
    use yappr_shared::entities::prelude::*;

    let Extension(db) = extract::<Extension<Arc<DatabaseConnection>>>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get DB connection: {}", e)))?;

    // Extract and check auth
    let auth_session = extract::<crate::auth::AuthSession>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get auth session: {}", e)))?;

    let auth_context = if let Some(user) = auth_session.user {
        AuthContext::load(&db, user.0.clone()).await
            .map_err(|e| ServerFnError::new(format!("Failed to load auth context: {}", e)))?
    } else {
        return Err(ServerFnError::new("Authentication required"));
    };

    // Load channel to check broadcaster ownership
    let channel = Channels::find_by_id(channel_id)
        .one(&*db)
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to load channel: {}", e)))?
        .ok_or_else(|| ServerFnError::new("Channel not found"))?;

    // Only admins or broadcaster owners can delete
    let can_delete = auth_context.is_admin()
        || auth_context.user.as_ref().map(|u| u.broadcaster_ids.contains(&channel.broadcaster_id)).unwrap_or(false);

    if !can_delete {
        return Err(ServerFnError::new("Permission denied"));
    }

    // Delete the channel (CASCADE will handle related records)
    Channels::delete_by_id(channel_id)
        .exec(&*db)
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to delete channel: {}", e)))?;

    Ok(())
}
