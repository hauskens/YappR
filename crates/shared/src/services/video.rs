use crate::entities::sea_orm_active_enums::Videotype;
use crate::entities::{prelude::*, video};
use sea_orm::{
    ActiveModelTrait, ColumnTrait, DatabaseConnection, DbErr, EntityTrait, QueryFilter, QueryOrder,
    QuerySelect, Set,
};
use tracing::{info, instrument};

/// Simple video service for basic CRUD operations (no authorization)
pub struct VideoService;

impl VideoService {
    /// Get all videos from the database
    #[instrument(level = "info", skip(db))]
    pub async fn get_all(db: &DatabaseConnection) -> Result<Vec<video::Model>, DbErr> {
        info!("Fetching all videos");

        let videos = Video::find().all(db).await?;

        info!(count = videos.len(), "Retrieved videos");
        Ok(videos)
    }

    /// Get a video by its ID
    #[instrument(level = "info", skip(db))]
    pub async fn get_by_id(
        db: &DatabaseConnection,
        id: i32,
    ) -> Result<Option<video::Model>, DbErr> {
        info!(video_id = id, "Fetching video by ID");

        let video = Video::find_by_id(id).one(db).await?;

        match &video {
            Some(_) => info!(video_id = id, "Video found"),
            None => info!(video_id = id, "Video not found"),
        }

        Ok(video)
    }

    /// Get a video by platform reference
    #[instrument(level = "info", skip(db))]
    pub async fn get_by_platform_ref(
        db: &DatabaseConnection,
        platform_ref: &str,
    ) -> Result<Option<video::Model>, DbErr> {
        info!(
            platform_ref = platform_ref,
            "Fetching video by platform_ref"
        );

        let video = Video::find()
            .filter(video::Column::PlatformRef.eq(platform_ref))
            .one(db)
            .await?;

        match &video {
            Some(v) => info!(video_id = v.id, platform_ref = platform_ref, "Video found"),
            None => info!(platform_ref = platform_ref, "Video not found"),
        }

        Ok(video)
    }

    /// Get all videos for a specific channel
    #[instrument(level = "info", skip(db))]
    pub async fn get_by_channel(
        db: &DatabaseConnection,
        channel_id: i32,
    ) -> Result<Vec<video::Model>, DbErr> {
        info!(channel_id = channel_id, "Fetching videos for channel");

        let videos = Video::find()
            .filter(video::Column::ChannelId.eq(channel_id))
            .all(db)
            .await?;

        info!(
            channel_id = channel_id,
            count = videos.len(),
            "Retrieved videos for channel"
        );
        Ok(videos)
    }

    /// Get only active videos
    #[instrument(level = "info", skip(db))]
    pub async fn get_active(db: &DatabaseConnection) -> Result<Vec<video::Model>, DbErr> {
        info!("Fetching active videos");

        let videos = Video::find()
            .filter(video::Column::Active.eq(true))
            .all(db)
            .await?;

        info!(count = videos.len(), "Retrieved active videos");
        Ok(videos)
    }

    /// Get videos by video type
    #[instrument(level = "info", skip(db))]
    pub async fn get_by_type(
        db: &DatabaseConnection,
        video_type: Videotype,
    ) -> Result<Vec<video::Model>, DbErr> {
        let type_str = format!("{:?}", video_type);
        info!(video_type = type_str, "Fetching videos by type");

        let videos = Video::find()
            .filter(video::Column::VideoType.eq(video_type))
            .all(db)
            .await?;

        info!(
            video_type = type_str,
            count = videos.len(),
            "Retrieved videos by type"
        );
        Ok(videos)
    }

    /// Get recent videos (ordered by upload date, limited by count)
    #[instrument(level = "info", skip(db))]
    pub async fn get_recent(
        db: &DatabaseConnection,
        limit: u64,
    ) -> Result<Vec<video::Model>, DbErr> {
        info!(limit = limit, "Fetching recent videos");

        let videos = Video::find()
            .order_by_desc(video::Column::Uploaded)
            .limit(limit)
            .all(db)
            .await?;

        info!(
            limit = limit,
            count = videos.len(),
            "Retrieved recent videos"
        );
        Ok(videos)
    }

    /// Get active videos for a specific channel
    #[instrument(level = "info", skip(db))]
    pub async fn get_active_by_channel(
        db: &DatabaseConnection,
        channel_id: i32,
    ) -> Result<Vec<video::Model>, DbErr> {
        info!(
            channel_id = channel_id,
            "Fetching active videos for channel"
        );

        let videos = Video::find()
            .filter(video::Column::ChannelId.eq(channel_id))
            .filter(video::Column::Active.eq(true))
            .all(db)
            .await?;

        info!(
            channel_id = channel_id,
            count = videos.len(),
            "Retrieved active videos for channel"
        );
        Ok(videos)
    }

    /// Get oldest active videos by platform (ordered by last_updated ASC)
    #[instrument(level = "info", skip(db))]
    pub async fn get_oldest_active_videos_by_platform(
        db: &DatabaseConnection,
        platform: &str,
        limit: u64,
    ) -> Result<Vec<video::Model>, DbErr> {
        info!(
            platform = platform,
            limit = limit,
            "Fetching oldest active videos by platform"
        );

        // Join with channels to filter by platform
        let videos = Video::find()
            .filter(video::Column::Active.eq(true))
            .filter(video::Column::PlatformRef.like(format!("{}:%", platform)))
            .order_by_asc(video::Column::LastUpdated)
            .limit(limit)
            .all(db)
            .await?;

        info!(
            platform = platform,
            limit = limit,
            count = videos.len(),
            "Retrieved oldest active videos"
        );
        Ok(videos)
    }

    /// Deactivate a video by setting active=false
    #[instrument(level = "info", skip(db))]
    pub async fn deactivate_video(
        db: &DatabaseConnection,
        video_id: i32,
    ) -> Result<video::Model, DbErr> {
        info!(video_id = video_id, "Deactivating video");

        let video = Video::find_by_id(video_id)
            .one(db)
            .await?
            .ok_or(DbErr::RecordNotFound(format!(
                "Video with ID {} not found",
                video_id
            )))?;

        let mut active_video: video::ActiveModel = video.into();
        active_video.active = Set(false);

        let updated = active_video.update(db).await?;

        info!(video_id = video_id, "Video deactivated");
        Ok(updated)
    }

    /// Update video metadata (title, duration, thumbnail)
    #[instrument(level = "info", skip(db))]
    pub async fn update_video_metadata(
        db: &DatabaseConnection,
        video_id: i32,
        title: Option<String>,
        duration: Option<f64>,
        thumbnail: Option<serde_json::Value>,
    ) -> Result<video::Model, DbErr> {
        info!(video_id = video_id, "Updating video metadata");

        let video = Video::find_by_id(video_id)
            .one(db)
            .await?
            .ok_or(DbErr::RecordNotFound(format!(
                "Video with ID {} not found",
                video_id
            )))?;

        let mut active_video: video::ActiveModel = video.into();

        if let Some(t) = title {
            active_video.title = Set(t);
        }
        if let Some(d) = duration {
            active_video.duration = Set(d);
        }
        if let Some(thumb) = thumbnail {
            active_video.thumbnail = Set(Some(thumb));
        }

        // Always update last_updated timestamp
        active_video.last_updated = Set(chrono::Utc::now().naive_utc());

        let updated = active_video.update(db).await?;

        info!(video_id = video_id, "Video metadata updated");
        Ok(updated)
    }
}
