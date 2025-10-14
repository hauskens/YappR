use sea_orm::{DatabaseConnection, EntityTrait, QueryFilter, ColumnTrait, DbErr};
use crate::entities::{prelude::*, channels};
use tracing::{info, instrument};

/// Simple example service for querying channels
pub struct ChannelService;

impl ChannelService {
    /// Get all channels from the database
    #[instrument(level = "info", skip(db))]
    pub async fn get_all_channels(db: &DatabaseConnection) -> Result<Vec<channels::Model>, DbErr> {
        info!("Fetching all channels");

        let channels = Channels::find()
            .all(db)
            .await?;

        info!(count = channels.len(), "Retrieved channels");
        Ok(channels)
    }

    /// Get a channel by its ID
    #[instrument(level = "info", skip(db))]
    pub async fn get_channel_by_id(db: &DatabaseConnection, id: i32) -> Result<Option<channels::Model>, DbErr> {
        info!(channel_id = id, "Fetching channel by ID");

        let channel = Channels::find_by_id(id)
            .one(db)
            .await?;

        match &channel {
            Some(_) => info!(channel_id = id, "Channel found"),
            None => info!(channel_id = id, "Channel not found"),
        }

        Ok(channel)
    }

    /// Get a channel by platform reference
    #[instrument(level = "info", skip(db))]
    pub async fn get_channel_by_platform_ref(db: &DatabaseConnection, platform_ref: &str) -> Result<Option<channels::Model>, DbErr> {
        info!(platform_ref = platform_ref, "Fetching channel by platform_ref");

        let channel = Channels::find()
            .filter(channels::Column::PlatformRef.eq(platform_ref))
            .one(db)
            .await?;

        match &channel {
            Some(c) => info!(channel_id = c.id, platform_ref = platform_ref, "Channel found"),
            None => info!(platform_ref = platform_ref, "Channel not found"),
        }

        Ok(channel)
    }

    /// Get all channels for a specific broadcaster
    #[instrument(level = "info", skip(db))]
    pub async fn get_channels_by_broadcaster(db: &DatabaseConnection, broadcaster_id: i32) -> Result<Vec<channels::Model>, DbErr> {
        info!(broadcaster_id = broadcaster_id, "Fetching channels for broadcaster");

        let channels = Channels::find()
            .filter(channels::Column::BroadcasterId.eq(broadcaster_id))
            .all(db)
            .await?;

        info!(broadcaster_id = broadcaster_id, count = channels.len(), "Retrieved channels for broadcaster");
        Ok(channels)
    }

    /// Get a channel by platform channel ID
    #[instrument(level = "info", skip(db))]
    pub async fn get_channel_by_platform_channel_id(db: &DatabaseConnection, platform_channel_id: &str) -> Result<Option<channels::Model>, DbErr> {
        info!(platform_channel_id = platform_channel_id, "Fetching channel by platform_channel_id");

        let channel = Channels::find()
            .filter(channels::Column::PlatformChannelId.eq(platform_channel_id))
            .one(db)
            .await?;

        match &channel {
            Some(c) => info!(channel_id = c.id, platform_channel_id = platform_channel_id, "Channel found"),
            None => info!(platform_channel_id = platform_channel_id, "Channel not found"),
        }

        Ok(channel)
    }
    /// Get channels by platform name
    #[instrument(level = "info", skip(db))]
    pub async fn get_channels_by_platform(db: &DatabaseConnection, platform_name: &str) -> Result<Vec<channels::Model>, DbErr> {
        info!(platform_name = platform_name, "Fetching channels by platform");

        let channels = Channels::find()
            .filter(channels::Column::PlatformName.eq(platform_name))
            .all(db)
            .await?;

        info!(platform_name = platform_name, count = channels.len(), "Retrieved channels for platform");
        Ok(channels)
    }
}
