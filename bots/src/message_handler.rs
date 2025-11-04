use crate::services::{BotUserService, ChatlogService};
use regex::Regex;
use sea_orm::DatabaseConnection;
use std::collections::HashMap;
use std::sync::{Arc, LazyLock};
use tracing::{error, info, instrument, warn};
use twitch_api::eventsub::channel::chat::ChannelChatMessageV1Payload;
use yappr_shared::models::{
    enums::ChannelRole,
    platforms::{BasePlatform, PlatformVariant},
};
use yappr_shared::services::content_submission::ContentSubmissionService;

/// Regex to extract URLs from chat messages
static URL_REGEX: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"https?://[^\s]+").expect("Failed to compile URL regex"));

/// Settings for a channel (cached from database)
#[derive(Clone, Debug)]
pub struct ChannelSettings {
    pub channel_id: i32,
    pub broadcaster_id: i32,
    pub content_queue_enabled: bool,
    pub chat_collection_enabled: bool,
}

pub struct MessageHandler {
    db: DatabaseConnection,
    chatlog_service: Arc<ChatlogService>,
    user_service: Arc<BotUserService>,
}

impl MessageHandler {
    pub fn new(
        db: DatabaseConnection,
        chatlog_service: Arc<ChatlogService>,
        user_service: Arc<BotUserService>,
    ) -> Self {
        Self {
            db,
            chatlog_service,
            user_service,
        }
    }

    /// Process a Twitch chat message
    #[instrument(level = "info", skip(self, message, settings), fields(
        chatter_user_id = %message.chatter_user_id,
        broadcaster_user_id = %message.broadcaster_user_id,
    ))]
    pub async fn handle_message(
        &self,
        message: &ChannelChatMessageV1Payload,
        settings: &ChannelSettings,
    ) -> Result<(), eyre::Report> {
        // Extract badges
        let badges = Self::extract_badges(message);

        // Update user role based on badges
        if let Err(e) = self.update_user_role(message, settings, &badges).await {
            warn!(error = %e, "Failed to update user role");
        }

        // Handle content queue submissions if enabled
        if settings.content_queue_enabled
            && let Err(e) = self.handle_content_queue(message, settings).await
        {
            error!(error = %e, "Failed to handle content queue");
        }

        // Store chat message if collection enabled
        if settings.chat_collection_enabled
            && let Err(e) = self.store_chat_message(message, settings).await
        {
            error!(error = %e, "Failed to store chat message");
        }

        Ok(())
    }

    /// Extract badges from message into a HashMap
    fn extract_badges(message: &ChannelChatMessageV1Payload) -> HashMap<String, String> {
        message
            .badges
            .iter()
            .map(|badge| (badge.set_id.to_string(), badge.id.to_string()))
            .collect()
    }

    /// Update user role based on Twitch badges
    async fn update_user_role(
        &self,
        message: &ChannelChatMessageV1Payload,
        settings: &ChannelSettings,
        badges: &HashMap<String, String>,
    ) -> Result<(), eyre::Report> {
        // Get or create user
        let color_str = format!("#{}", message.color.as_str());
        let user = self
            .user_service
            .get_or_create_user(
                message.chatter_user_id.as_str(),
                message.chatter_user_name.as_str(),
                Some(&color_str),
            )
            .await?;

        // Determine role from badges
        for key in badges.keys() {
            if let Some(role) = ChannelRole::from_platform_badge(&BasePlatform::Twitch, key) {
                // Update role in database
                info!(
                    user_id = user.id,
                    role = role.clone().to_string(),
                    "Updating user role"
                );
                self.user_service
                    .update_user_role(user, settings.channel_id, &role)
                    .await?;
                return Ok(());
            }
        }

        Ok(())
    }

    /// Handle content queue URL submissions
    async fn handle_content_queue(
        &self,
        message: &ChannelChatMessageV1Payload,
        settings: &ChannelSettings,
    ) -> Result<(), eyre::Report> {
        // Extract URLs from message
        let urls: Vec<&str> = URL_REGEX
            .find_iter(&message.message.text)
            .map(|m| m.as_str())
            .collect();

        if urls.is_empty() {
            return Ok(());
        }

        // Extract user comment once before processing URLs
        let _user_comment = self.extract_user_comment(&message.message.text, &urls);

        // Process each URL
        for url in &urls {
            // Check if it's a supported platform
            if PlatformVariant::from_url(url).is_none() {
                continue; // Skip unsupported URLs
            }

            info!(
                url = url,
                broadcaster_id = settings.broadcaster_id,
                user = %message.chatter_user_name,
                "Submitting URL to content queue"
            );

            // Use shared ContentSubmissionService
            match ContentSubmissionService::submit_url(
                &self.db,
                url,
                settings.broadcaster_id,
                0,   // TODO: Get actual user_id from database lookup
                1.0, // Default submission weight
            )
            .await
            {
                Ok((queue_entry, is_new)) => {
                    info!(
                        queue_id = queue_entry.id,
                        is_new = is_new,
                        "Successfully submitted URL to queue"
                    );
                }
                Err(e) => {
                    error!(error = %e, url = url, "Failed to submit URL to queue");
                }
            }
        }

        Ok(())
    }

    /// Extract user comment from message, replacing/removing URLs
    fn extract_user_comment(&self, text: &str, urls: &[&str]) -> Option<String> {
        let mut comment = text.to_string();

        for url in urls {
            // Check if URL is at start or end of message
            let trimmed = comment.trim();
            if trimmed.starts_with(url) || trimmed.ends_with(url) {
                // Remove URL entirely
                comment = comment.replace(url, "");
            } else {
                // Replace URL with <link> if in middle
                comment = comment.replace(url, "<link>");
            }
        }

        let comment = comment.trim().to_string();
        if comment.is_empty() {
            None
        } else {
            Some(comment)
        }
    }

    /// Store chat message in database
    async fn store_chat_message(
        &self,
        message: &ChannelChatMessageV1Payload,
        settings: &ChannelSettings,
    ) -> Result<(), eyre::Report> {
        // Use current timestamp since event doesn't include message timestamp
        let timestamp = chrono::Utc::now().naive_utc();

        self.chatlog_service
            .add_message(
                settings.channel_id,
                timestamp,
                message.chatter_user_name.to_string(),
                message.message.text.clone(),
                None, // TODO: Store external_user_account_id
            )
            .await?;

        Ok(())
    }
}
