use crate::discord::DiscordMessage;
use crate::services::{ChatlogService, user_service::BotUserService};
use sea_orm::DatabaseConnection;
use serenity::all::Message;
use std::sync::Arc;
use yappr_shared::models::channel::ChannelSettings;

/// Discord message handler wrapper
/// Converts Discord-specific messages to generic PlatformMessage and delegates to core handler
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

    /// Process a Discord message
    pub async fn handle_message(
        &self,
        message: Message,
        settings: &ChannelSettings,
    ) -> Result<(), eyre::Report> {
        // Convert Discord message to generic message type
        let discord_message = DiscordMessage::new(message, settings.broadcaster_id);

        // Create generic handler and delegate
        let handler = crate::core::MessageHandler::new(
            self.db.clone(),
            self.chatlog_service.clone(),
            self.user_service.clone(),
        );

        handler.handle_message(&discord_message, settings).await
    }
}
