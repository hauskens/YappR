use crate::services::{ChatlogService, user_service::BotUserService};
use crate::twitch::TwitchMessage;
use sea_orm::DatabaseConnection;
use std::sync::Arc;
use tracing::instrument;
use twitch_api::eventsub::channel::chat::ChannelChatMessageV1Payload;
use yappr_shared::models::channel::ChannelSettings;

/// Twitch message handler wrapper
/// Converts Twitch-specific payloads to generic PlatformMessage and delegates to core handler
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
        // Convert Twitch payload to generic message type
        let twitch_message = TwitchMessage::new(message);

        // Create generic handler and delegate
        let handler = crate::core::MessageHandler::new(
            self.db.clone(),
            self.chatlog_service.clone(),
            self.user_service.clone(),
        );

        handler.handle_message(&twitch_message, settings).await
    }
}
