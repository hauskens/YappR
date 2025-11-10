use crate::services::{ChatlogService, user_service::BotUserService};
use hex_color::HexColor;
use regex::Regex;
use sea_orm::DatabaseConnection;
use std::collections::HashMap;
use std::sync::{Arc, LazyLock};
use tracing::{error, info, instrument, warn};
use yappr_shared::models::{
    channel::ChannelSettings,
    enums::ChannelRole,
    platforms::{AccountPlatform, PlatformVariant},
};
use yappr_shared::services::content_submission::ContentSubmissionService;
use yappr_shared::user::UserService;

/// Regex to extract URLs from chat messages
static URL_REGEX: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"https?://[^\s]+").expect("Failed to compile URL regex"));

/// Platform-agnostic message trait
/// Each bot platform implements this trait to provide a unified interface
pub trait PlatformMessage {
    /// Unique user ID on the platform
    fn user_id(&self) -> &str;

    /// Username/display name
    fn username(&self) -> &str;

    /// User's color in chat (if available)
    fn user_color(&self) -> Option<HexColor>;

    /// The text content of the message
    fn message_text(&self) -> &str;

    /// When the message was sent
    fn timestamp(&self) -> chrono::NaiveDateTime;

    /// Broadcaster/channel ID where message was sent
    fn broadcaster_id(&self) -> &str;

    /// Extract platform-specific badges/roles
    fn extract_badges(&self) -> HashMap<String, String>;

    /// The platform this message came from
    fn platform(&self) -> AccountPlatform;

    /// URL to the user's avatar (if available)
    fn avatar_url(&self) -> Option<&str>;
}

/// Generic message handler that works with any platform implementing PlatformMessage
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

    /// Process a chat message from any platform
    #[instrument(level = "trace", skip(self, message, settings), fields(
        user_id = %message.user_id(),
        broadcaster_id = %message.broadcaster_id(),
    ))]
    pub async fn handle_message<M: PlatformMessage>(
        &self,
        message: &M,
        settings: &ChannelSettings,
    ) -> Result<(), eyre::Report> {
        // Extract badges
        let badges = message.extract_badges();

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

    /// Update user role based on platform badges
    async fn update_user_role<M: PlatformMessage>(
        &self,
        message: &M,
        settings: &ChannelSettings,
        badges: &HashMap<String, String>,
    ) -> Result<(), eyre::Report> {
        // Get or create user
        let user = self
            .user_service
            .get_or_create_user(
                message.user_id(),
                message.username(),
                message.user_color().as_ref(),
                message.avatar_url(),
            )
            .await?;

        // Determine role from badges
        for key in badges.keys() {
            if let Some(role) = ChannelRole::from_platform_badge(&message.platform(), key) {
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
    async fn handle_content_queue<M: PlatformMessage>(
        &self,
        message: &M,
        settings: &ChannelSettings,
    ) -> Result<(), eyre::Report> {
        // Extract URLs from message
        let urls: Vec<&str> = URL_REGEX
            .find_iter(message.message_text())
            .map(|m| m.as_str())
            .collect();

        if urls.is_empty() {
            return Ok(());
        }

        let user = UserService::get_or_create_user(
            &self.db,
            message.user_id(),
            message.username(),
            message.platform(),
            message.user_color().as_ref(),
            None,
        )
        .await?;

        // Extract user comment once before processing URLs
        let _user_comment = self.extract_user_comment(message.message_text(), &urls);

        // Process each URL
        for url in &urls {
            // Check if it's a supported platform
            if PlatformVariant::from_url(url).is_none() {
                continue; // Skip unsupported URLs
            }

            info!(
                url = url,
                broadcaster_id = settings.broadcaster_id,
                user = %message.username(),
                "Submitting URL to content queue"
            );

            // Use shared ContentSubmissionService
            match ContentSubmissionService::submit_url(
                &self.db,
                url,
                settings.broadcaster_id,
                user.id,
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
    async fn store_chat_message<M: PlatformMessage>(
        &self,
        message: &M,
        settings: &ChannelSettings,
    ) -> Result<(), eyre::Report> {
        let timestamp = message.timestamp();

        self.chatlog_service
            .add_message(
                settings.channel_id,
                timestamp,
                message.username().to_string(),
                message.message_text().to_string(),
                None, // TODO: Store external_user_account_id
            )
            .await?;

        Ok(())
    }
}
