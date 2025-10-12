#[cfg(feature = "database")]
use crate::entities::{video, channels};
#[cfg(feature = "database")]
use sea_orm::*;
use crate::database::get_database_connection;

pub struct VideoService {
    db: DatabaseConnection,
}

impl VideoService {
    pub async fn new() -> Self {
        let db = get_database_connection().await.unwrap();
        Self { db }
    }

    /// Retrieves a video by its ID.
    ///
    /// # Arguments
    ///
    /// * `id` - The video ID to retrieve.
    pub async fn get_by_id(&self, id: i32) -> Result<Option<video::Model>, DbErr> {
        let video = video::Entity::find_by_id(id)
            .one(&self.db)
            .await?;
        Ok(video)
    }

    /// Retrieves a video by its platform reference.
    ///
    /// # Arguments
    ///
    /// * `platform_ref` - The unique platform reference string.
    pub async fn get_by_platform_ref(&self, platform_ref: &str) -> Result<Option<video::Model>, DbErr> {
        let video = video::Entity::find()
            .filter(video::Column::PlatformRef.eq(platform_ref))
            .one(&self.db)
            .await?;
        Ok(video)
    }

    /// Retrieves all videos from the database.
    ///
    /// # Arguments
    ///
    /// * `active_only` - If true, only returns active videos.
    /// * `limit` - Optional limit on number of results.
    /// * `offset` - Optional offset for pagination.
    pub async fn list(&self, active_only: bool, limit: Option<u64>, offset: Option<u64>) -> Result<Vec<video::Model>, DbErr> {
        let mut query = video::Entity::find();

        if active_only {
            query = query.filter(video::Column::Active.eq(true));
        }

        if let Some(limit) = limit {
            query = query.limit(limit);
        }

        if let Some(offset) = offset {
            query = query.offset(offset);
        }

        // Order by most recently uploaded
        query = query.order_by_desc(video::Column::Uploaded);

        let videos = query.all(&self.db).await?;
        Ok(videos)
    }

    /// Retrieves all videos for a specific channel.
    ///
    /// # Arguments
    ///
    /// * `channel_id` - The channel ID to filter by.
    /// * `active_only` - If true, only returns active videos.
    /// * `limit` - Optional limit on number of results.
    /// * `offset` - Optional offset for pagination.
    pub async fn list_by_channel(&self, channel_id: i32, active_only: bool, limit: Option<u64>, offset: Option<u64>) -> Result<Vec<video::Model>, DbErr> {
        let mut query = video::Entity::find()
            .filter(video::Column::ChannelId.eq(channel_id));

        if active_only {
            query = query.filter(video::Column::Active.eq(true));
        }

        if let Some(limit) = limit {
            query = query.limit(limit);
        }

        if let Some(offset) = offset {
            query = query.offset(offset);
        }

        // Order by most recently uploaded
        query = query.order_by_desc(video::Column::Uploaded);

        let videos = query.all(&self.db).await?;
        Ok(videos)
    }

    /// Retrieves videos by video type.
    ///
    /// # Arguments
    ///
    /// * `video_type` - The video type to filter by.
    /// * `active_only` - If true, only returns active videos.
    /// * `limit` - Optional limit on number of results.
    pub async fn list_by_type(&self, video_type: crate::entities::sea_orm_active_enums::Videotype, active_only: bool, limit: Option<u64>) -> Result<Vec<video::Model>, DbErr> {
        let mut query = video::Entity::find()
            .filter(video::Column::VideoType.eq(video_type));

        if active_only {
            query = query.filter(video::Column::Active.eq(true));
        }

        if let Some(limit) = limit {
            query = query.limit(limit);
        }

        // Order by most recently uploaded
        query = query.order_by_desc(video::Column::Uploaded);

        let videos = query.all(&self.db).await?;
        Ok(videos)
    }

    /// Retrieves videos with their associated channel information.
    ///
    /// # Arguments
    ///
    /// * `video_id` - The video ID to retrieve.
    pub async fn get_with_channel(&self, video_id: i32) -> Result<Option<(video::Model, Option<channels::Model>)>, DbErr> {
        let result = video::Entity::find_by_id(video_id)
            .find_also_related(channels::Entity)
            .one(&self.db)
            .await?;

        Ok(result)
    }

    /// Retrieves multiple videos with their associated channels.
    ///
    /// # Arguments
    ///
    /// * `active_only` - If true, only returns active videos.
    /// * `limit` - Optional limit on number of results.
    pub async fn list_with_channels(&self, active_only: bool, limit: Option<u64>) -> Result<Vec<(video::Model, Option<channels::Model>)>, DbErr> {
        let mut query = video::Entity::find();

        if active_only {
            query = query.filter(video::Column::Active.eq(true));
        }

        if let Some(limit) = limit {
            query = query.limit(limit);
        }

        // Order by most recently uploaded
        query = query.order_by_desc(video::Column::Uploaded);

        let results = query
            .find_also_related(channels::Entity)
            .all(&self.db)
            .await?;

        Ok(results)
    }

    /// Inserts a new video into the database.
    ///
    /// # Arguments
    ///
    /// * `video` - The video data to insert.
    pub async fn insert(&self, video: video::ActiveModel) -> Result<video::Model, DbErr> {
        let result = video.insert(&self.db).await?;
        Ok(result)
    }

    /// Creates a new video with the provided data.
    ///
    /// # Arguments
    ///
    /// * `title` - The video title.
    /// * `video_type` - The video type.
    /// * `duration` - The video duration in seconds.
    /// * `channel_id` - The channel ID this video belongs to.
    /// * `platform_ref` - The platform reference/ID.
    /// * `uploaded` - The upload timestamp.
    /// * `thumbnail` - Optional thumbnail JSON data.
    /// * `audio` - Optional audio JSON data.
    pub async fn create(
        &self,
        title: String,
        video_type: crate::entities::sea_orm_active_enums::Videotype,
        duration: f64,
        channel_id: i32,
        platform_ref: String,
        uploaded: chrono::DateTime<chrono::Utc>,
        thumbnail: Option<serde_json::Value>,
        audio: Option<serde_json::Value>,
    ) -> Result<video::Model, DbErr> {
        let now = chrono::Utc::now();

        let video = video::ActiveModel {
            title: Set(title),
            video_type: Set(video_type),
            duration: Set(duration),
            channel_id: Set(channel_id),
            platform_ref: Set(platform_ref),
            uploaded: Set(uploaded.naive_utc()),
            thumbnail: Set(thumbnail),
            audio: Set(audio),
            last_updated: Set(now.naive_utc()),
            active: Set(true),
            estimated_upload_time: Set(None),
            ..Default::default()
        };

        self.insert(video).await
    }

    /// Updates a video's information.
    ///
    /// # Arguments
    ///
    /// * `id` - The video ID to update.
    /// * `video` - The updated video data.
    pub async fn update(&self, id: i32, video: video::ActiveModel) -> Result<video::Model, DbErr> {
        let mut video = video;
        video.id = Set(id);
        video.last_updated = Set(chrono::Utc::now().naive_utc());
        let result = video.update(&self.db).await?;
        Ok(result)
    }

    /// Updates a video's active status.
    ///
    /// # Arguments
    ///
    /// * `id` - The video ID to update.
    /// * `active` - The new active status.
    pub async fn set_active(&self, id: i32, active: bool) -> Result<video::Model, DbErr> {
        let video = video::ActiveModel {
            id: Set(id),
            active: Set(active),
            last_updated: Set(chrono::Utc::now().naive_utc()),
            ..Default::default()
        };

        video.update(&self.db).await
    }

    /// Deletes a video by its ID.
    ///
    /// # Arguments
    ///
    /// * `id` - The video ID to delete.
    pub async fn delete(&self, id: i32) -> Result<DeleteResult, DbErr> {
        let result = video::Entity::delete_by_id(id)
            .exec(&self.db)
            .await?;
        Ok(result)
    }

    /// Searches videos by title.
    ///
    /// # Arguments
    ///
    /// * `search_term` - The search term to look for in titles.
    /// * `active_only` - If true, only returns active videos.
    /// * `limit` - Optional limit on number of results.
    pub async fn search_by_title(&self, search_term: &str, active_only: bool, limit: Option<u64>) -> Result<Vec<video::Model>, DbErr> {
        let mut query = video::Entity::find()
            .filter(video::Column::Title.contains(search_term));

        if active_only {
            query = query.filter(video::Column::Active.eq(true));
        }

        if let Some(limit) = limit {
            query = query.limit(limit);
        }

        // Order by most recently uploaded
        query = query.order_by_desc(video::Column::Uploaded);

        let videos = query.all(&self.db).await?;
        Ok(videos)
    }

    /// Gets the total count of videos.
    ///
    /// # Arguments
    ///
    /// * `active_only` - If true, only counts active videos.
    pub async fn count(&self, active_only: bool) -> Result<u64, DbErr> {
        let mut query = video::Entity::find();

        if active_only {
            query = query.filter(video::Column::Active.eq(true));
        }

        let count = query.count(&self.db).await?;
        Ok(count)
    }

    /// Gets the total count of videos for a specific channel.
    ///
    /// # Arguments
    ///
    /// * `channel_id` - The channel ID to count videos for.
    /// * `active_only` - If true, only counts active videos.
    pub async fn count_by_channel(&self, channel_id: i32, active_only: bool) -> Result<u64, DbErr> {
        let mut query = video::Entity::find()
            .filter(video::Column::ChannelId.eq(channel_id));

        if active_only {
            query = query.filter(video::Column::Active.eq(true));
        }

        let count = query.count(&self.db).await?;
        Ok(count)
    }
}