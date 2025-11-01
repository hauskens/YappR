//! Server functions for search operations

use leptos::prelude::*;
use crate::server_fns::types::*;

#[cfg(feature = "ssr")]
use yappr_shared::services::{channel::ChannelService, search::SearchService};

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
    use chrono::{DateTime, NaiveDate, Utc};

    let Extension(db) = extract::<Extension<Arc<DatabaseConnection>>>()
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get DB connection: {}", e)))?;

    let all_channels = ChannelService::get_channels_by_broadcaster(&db, broadcaster_id)
        .await
        .map_err(|e| ServerFnError::new(format!("Failed to get channels: {}", e)))?;

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

    // Batch load channels
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

    let mut video_results = Vec::new();
    for result in results {
        match VideoResultData::from_model(result, &channel_map) {
            Ok(vr) => video_results.push(vr),
            Err(e) => return Err(ServerFnError::new(format!("Conversion error: {}", e))),
        }
    }

    Ok(video_results)
}
