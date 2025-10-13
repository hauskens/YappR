#[cfg(feature = "database")]
use crate::entities::channels;
#[cfg(feature = "database")]
use sea_orm::*;
use crate::models::platforms::VideoPlatform;
use crate::database::get_database_connection;
use tracing::{info, warn, error, instrument, debug};

pub struct ChannelService {
    db: DatabaseConnection,
}

impl ChannelService {
    #[instrument(level = "info")]
    pub async fn new() -> Self {
        info!("Creating new ChannelService instance");
        let db = get_database_connection().await.unwrap();
        Self { db }
    }

    /// Retrieves a channel by its ID.
    ///
    /// # Arguments
    ///
    /// * `id` - The channel ID to retrieve.
    #[instrument(level = "info", skip(self))]
    pub async fn get_by_id(&self, id: i32) -> Result<Option<channels::Model>, DbErr> {
        info!(channel_id = id, "Fetching channel by ID");
        match channels::Entity::find_by_id(id).one(&self.db).await {
            Ok(channel) => {
                match &channel {
                    Some(_) => info!(channel_id = id, "Channel found"),
                    None => info!(channel_id = id, "Channel not found"),
                }
                Ok(channel)
            }
            Err(e) => {
                error!(error = %e, channel_id = id, "Failed to fetch channel by ID");
                Err(e)
            }
        }
    }

    /// Retrieves a channel by its platform reference.
    ///
    /// # Arguments
    ///
    /// * `platform_ref` - The unique platform reference string.
    #[instrument(level = "info", skip(self))]
    pub async fn get_by_platform_ref(&self, platform_ref: &str) -> Result<Option<channels::Model>, DbErr> {
        info!(platform_ref = %platform_ref, "Fetching channel by platform reference");
        match channels::Entity::find()
            .filter(channels::Column::PlatformRef.eq(platform_ref))
            .one(&self.db)
            .await {
            Ok(channel) => {
                match &channel {
                    Some(_) => info!(platform_ref = %platform_ref, "Channel found"),
                    None => info!(platform_ref = %platform_ref, "Channel not found"),
                }
                Ok(channel)
            }
            Err(e) => {
                error!(error = %e, platform_ref = %platform_ref, "Failed to fetch channel by platform reference");
                Err(e)
            }
        }
    }

    /// Retrieves a channel by its platform channel ID.
    ///
    /// # Arguments
    ///
    /// * `platform_channel_id` - The unique platform channel ID.
    pub async fn get_by_platform_channel_id(&self, platform_channel_id: &str) -> Result<Option<channels::Model>, DbErr> {
        let channel = channels::Entity::find()
            .filter(channels::Column::PlatformChannelId.eq(platform_channel_id))
            .one(&self.db)
            .await?;
        Ok(channel)
    }

    /// Retrieves all channels from the database.
    ///
    /// # Arguments
    ///
    /// * `platform` - Optional platform filter. If provided, only returns channels for that platform.
    #[instrument(level = "info", skip(self))]
    pub async fn list(&self, platform: Option<VideoPlatform>) -> Result<Vec<channels::Model>, DbErr> {
        info!(platform = ?platform, "Fetching all channels");
        let mut query = channels::Entity::find();

        if let Some(platform) = platform {
            debug!(platform = %platform.as_str(), "Filtering by platform");
            query = query.filter(channels::Column::PlatformName.eq(platform.as_str()));
        }

        match query.all(&self.db).await {
            Ok(channels) => {
                info!(channel_count = channels.len(), platform = ?platform, "Successfully fetched channels");
                Ok(channels)
            }
            Err(e) => {
                error!(error = %e, platform = ?platform, "Failed to fetch channels");
                Err(e)
            }
        }
    }

    /// Retrieves all channels for a specific broadcaster.
    ///
    /// # Arguments
    ///
    /// * `broadcaster_id` - The broadcaster ID to filter by.
    /// * `platform` - Optional platform filter.
    pub async fn list_by_broadcaster(&self, broadcaster_id: i32, platform: Option<VideoPlatform>) -> Result<Vec<channels::Model>, DbErr> {
        let mut query = channels::Entity::find()
            .filter(channels::Column::BroadcasterId.eq(broadcaster_id));

        if let Some(platform) = platform {
            query = query.filter(channels::Column::PlatformName.eq(platform.as_str()));
        }

        let channels = query.all(&self.db).await?;
        Ok(channels)
    }

    /// Inserts a new channel into the database.
    ///
    /// # Arguments
    ///
    /// * `channel` - The channel data to insert.
    pub async fn insert(&self, channel: channels::ActiveModel) -> Result<channels::Model, DbErr> {
        let result = channel.insert(&self.db).await?;
        Ok(result)
    }

    /// Creates a new channel with the provided data.
    ///
    /// # Arguments
    ///
    /// * `name` - The channel name.
    /// * `broadcaster_id` - The broadcaster ID this channel belongs to.
    /// * `platform_ref` - Unique platform reference string.
    /// * `main_video_type` - The main video type for this channel.
    /// * `platform_channel_id` - Unique platform channel ID.
    /// * `platform_name` - The platform name (e.g., "youtube", "twitch").
    /// * `source_channel_id` - Optional source channel ID.
    #[instrument(level = "info", skip(self))]
    pub async fn create(
        &self,
        name: String,
        broadcaster_id: i32,
        platform_ref: String,
        main_video_type: crate::entities::sea_orm_active_enums::Videotype,
        platform_channel_id: String,
        platform_name: String,
        source_channel_id: Option<i32>,
    ) -> Result<channels::Model, DbErr> {
        info!(
            name = %name,
            broadcaster_id = broadcaster_id,
            platform_ref = %platform_ref,
            platform_name = %platform_name,
            "Creating new channel"
        );

        let channel = channels::ActiveModel {
            name: Set(name),
            broadcaster_id: Set(broadcaster_id),
            platform_ref: Set(platform_ref),
            main_video_type: Set(main_video_type),
            platform_channel_id: Set(platform_channel_id),
            platform_name: Set(platform_name),
            source_channel_id: Set(source_channel_id),
            last_active: Set(None),
            ..Default::default()
        };

        match self.insert(channel).await {
            Ok(channel) => {
                info!(channel_id = channel.id, name = %channel.name, "Channel created successfully");
                Ok(channel)
            }
            Err(e) => {
                error!(error = %e, broadcaster_id = broadcaster_id, "Failed to create channel");
                Err(e)
            }
        }
    }

    /// Updates a channel's information.
    ///
    /// # Arguments
    ///
    /// * `id` - The channel ID to update.
    /// * `channel` - The updated channel data.
    pub async fn update(&self, id: i32, channel: channels::ActiveModel) -> Result<channels::Model, DbErr> {
        let mut channel = channel;
        channel.id = Set(id);
        let result = channel.update(&self.db).await?;
        Ok(result)
    }

    /// Deletes a channel by its ID.
    ///
    /// # Arguments
    ///
    /// * `id` - The channel ID to delete.
    #[instrument(level = "warn", skip(self))]
    pub async fn delete(&self, id: i32) -> Result<DeleteResult, DbErr> {
        warn!(channel_id = id, "Deleting channel");
        match channels::Entity::delete_by_id(id).exec(&self.db).await {
            Ok(result) => {
                info!(channel_id = id, rows_affected = result.rows_affected, "Channel deleted successfully");
                Ok(result)
            }
            Err(e) => {
                error!(error = %e, channel_id = id, "Failed to delete channel");
                Err(e)
            }
        }
    }

    /// Updates the last_active timestamp for a channel.
    ///
    /// # Arguments
    ///
    /// * `id` - The channel ID to update.
    /// * `timestamp` - Optional timestamp. If None, sets to current time.
    pub async fn update_last_active(&self, id: i32, timestamp: Option<chrono::DateTime<chrono::Utc>>) -> Result<channels::Model, DbErr> {
        let timestamp = timestamp.unwrap_or_else(|| chrono::Utc::now());

        let channel = channels::ActiveModel {
            id: Set(id),
            last_active: Set(Some(timestamp.naive_utc())),
            ..Default::default()
        };

        channel.update(&self.db).await
    }
}