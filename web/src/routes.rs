use axum::{
    extract::{Extension, Path},
    http::{StatusCode, header},
    response::Response,
};
use sea_orm::{DatabaseConnection, EntityTrait};
use std::sync::Arc;
use yappr_shared::config::Config;
use yappr_shared::entities::prelude::*;
use yappr_shared::models::{FileStorageTrait, get_file};

/// Handler for serving video thumbnails
pub async fn serve_thumbnail(
    Path(video_id): Path<i32>,
    Extension(db): Extension<Arc<DatabaseConnection>>,
    Extension(config): Extension<Arc<Config>>,
) -> Result<Response, StatusCode> {
    tracing::info!("Thumbnail request for video_id: {}", video_id);

    // Get video from database
    let video = Video::find_by_id(video_id)
        .one(db.as_ref())
        .await
        .map_err(|e| {
            tracing::error!("Database error fetching video {}: {:?}", video_id, e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?
        .ok_or_else(|| {
            tracing::warn!("Video {} not found in database", video_id);
            StatusCode::NOT_FOUND
        })?;

    tracing::debug!("Found video: {:?}", video.id);

    // Get file storage information from video
    let file_storage = video.get_file_storage().map_err(|e| {
        tracing::warn!("No thumbnail available for video {}: {}", video_id, e);
        StatusCode::NOT_FOUND
    })?;

    tracing::debug!(
        "File storage info: upload_storage={}, filename={}",
        file_storage.upload_storage,
        file_storage.filename
    );

    // Build path from storage location, upload_storage directory, and filename
    let thumbnail_path = get_file(&config, &file_storage).map_err(|e| {
        tracing::error!("Failed to get thumbnail path: {}", e);
        StatusCode::NOT_FOUND
    })?;

    tracing::info!("Looking for thumbnail at path: {:?}", thumbnail_path);

    // Read thumbnail file
    let content = tokio::fs::read(&thumbnail_path).await.map_err(|e| {
        tracing::error!(
            "Failed to read thumbnail file {:?}: {:?}",
            thumbnail_path,
            e
        );
        StatusCode::NOT_FOUND
    })?;

    tracing::info!("Successfully read thumbnail, size: {} bytes", content.len());

    // Determine content type from the stored content_type or filename
    let content_type = if !file_storage.content_type.is_empty() {
        file_storage.content_type.as_str()
    } else {
        "image/jpeg"
    };

    tracing::debug!("Serving thumbnail with content-type: {}", content_type);

    // Build response with caching headers
    Response::builder()
        .status(StatusCode::OK)
        .header(header::CONTENT_TYPE, content_type)
        .header(header::CACHE_CONTROL, "public, max-age=31536000, immutable")
        .body(axum::body::Body::from(content))
        .map_err(|e| {
            tracing::error!("Failed to build response: {:?}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })
}
