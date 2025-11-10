use crate::twitch::TwitchModerationEvent;
use sea_orm::DatabaseConnection;
use tracing::instrument;
use twitch_api::eventsub::channel::chat::ChannelChatClearUserMessagesV1Payload;

/// Twitch moderation handler wrapper
/// Converts Twitch-specific payloads to generic PlatformModerationEvent and delegates to core handler
pub struct ModerationHandler {
    db: DatabaseConnection,
}

impl ModerationHandler {
    pub fn new(db: DatabaseConnection) -> Self {
        Self { db }
    }

    /// Handle user timeout/ban event
    #[instrument(level = "info", skip(self, event), fields(
        target_user_id = %event.target_user_id,
        broadcaster_user_id = %event.broadcaster_user_id,
    ))]
    pub async fn handle_moderation_event(
        &self,
        event: &ChannelChatClearUserMessagesV1Payload,
        channel_id: i32,
        broadcaster_id: i32,
    ) -> Result<(), eyre::Report> {
        // Convert Twitch payload to generic moderation event type
        let twitch_event = TwitchModerationEvent::new(event);

        // Create generic handler and delegate
        let handler = crate::core::ModerationHandler::new(self.db.clone());

        handler
            .handle_moderation_event(&twitch_event, channel_id, broadcaster_id)
            .await
    }
}
