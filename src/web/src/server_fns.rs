//! Server functions for interacting with the database
use leptos::prelude::*;
use serde::{Deserialize, Serialize};

#[cfg(feature = "ssr")]
use yappr_shared::services::channel::ChannelService;

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
