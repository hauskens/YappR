use crate::message_handler::ChannelSettings;
use sea_orm::{ColumnTrait, DatabaseConnection, EntityTrait, QueryFilter};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;
use tokio::time::{interval, Duration};
use tracing::{info, instrument};
use yappr_shared::entities::{channels, prelude::*};

/// Manages channel subscriptions and settings cache
pub struct ChannelManager {
    db: DatabaseConnection,
    /// Cache of channel settings: platform_channel_id -> ChannelSettings
    settings_cache: Arc<RwLock<HashMap<String, ChannelSettings>>>,
    check_interval: Duration,
}

impl ChannelManager {
    pub fn new(db: DatabaseConnection) -> Self {
        Self {
            db,
            settings_cache: Arc::new(RwLock::new(HashMap::new())),
            check_interval: Duration::from_secs(60),
        }
    }

    /// Get settings for a channel by platform_channel_id (broadcaster_user_id from Twitch)
    pub async fn get_settings(&self, platform_channel_id: &str) -> Option<ChannelSettings> {
        let cache = self.settings_cache.read().await;
        cache.get(platform_channel_id).cloned()
    }

    /// Get all enabled channel IDs (broadcaster_user_ids) for subscription
    pub async fn get_enabled_channel_ids(&self) -> Vec<String> {
        let cache = self.settings_cache.read().await;
        cache
            .iter()
            .filter(|(_, settings)| settings.chat_collection_enabled || settings.content_queue_enabled)
            .map(|(channel_id, _)| channel_id.clone())
            .collect()
    }

    /// Refresh channel settings from database
    #[instrument(level = "info", skip(self))]
    pub async fn refresh_settings(&self) -> Result<(), eyre::Report> {
        // Query all Twitch channels with their settings
        let channels_with_settings = Channels::find()
            .find_also_related(ChannelSettings)
            .filter(channels::Column::PlatformName.eq("twitch"))
            .all(&self.db)
            .await?;

        let mut new_cache = HashMap::new();

        for (channel, settings_opt) in channels_with_settings {
            if let Some(settings) = settings_opt {
                // Only cache if chat collection or content queue is enabled
                if settings.chat_collection_enabled || settings.content_queue_enabled {
                    new_cache.insert(
                        channel.platform_channel_id.clone(),
                        ChannelSettings {
                            channel_id: channel.id,
                            broadcaster_id: channel.broadcaster_id,
                            content_queue_enabled: settings.content_queue_enabled,
                            chat_collection_enabled: settings.chat_collection_enabled,
                        },
                    );
                }
            }
        }

        let count = new_cache.len();

        // Update cache
        let mut cache = self.settings_cache.write().await;
        *cache = new_cache;

        info!(enabled_channels = count, "Refreshed channel settings cache");

        Ok(())
    }

    /// Start periodic refresh task
    pub async fn start_periodic_refresh(self: Arc<Self>) -> Result<(), eyre::Report> {
        // Do initial refresh
        self.refresh_settings().await?;

        let mut refresh_timer = interval(self.check_interval);

        loop {
            refresh_timer.tick().await;

            if let Err(e) = self.refresh_settings().await {
                tracing::error!(error = %e, "Failed to refresh channel settings");
            }
        }
    }

    /// Get list of channel IDs that changed (new channels to subscribe, old channels to unsubscribe)
    pub async fn get_channel_changes(&self, current_subscriptions: &[String]) -> (Vec<String>, Vec<String>) {
        let cache = self.settings_cache.read().await;
        let enabled_channels: Vec<String> = cache
            .iter()
            .filter(|(_, settings)| settings.chat_collection_enabled || settings.content_queue_enabled)
            .map(|(channel_id, _)| channel_id.clone())
            .collect();

        let to_subscribe: Vec<String> = enabled_channels
            .iter()
            .filter(|id| !current_subscriptions.contains(id))
            .cloned()
            .collect();

        let to_unsubscribe: Vec<String> = current_subscriptions
            .iter()
            .filter(|id| !enabled_channels.contains(id))
            .cloned()
            .collect();

        (to_subscribe, to_unsubscribe)
    }
}
