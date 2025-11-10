use crate::core::PlatformModerationEvent;
use twitch_api::eventsub::channel::chat::ChannelChatClearUserMessagesV1Payload;
use yappr_shared::models::platforms::AccountPlatform;

/// Wrapper around Twitch's clear user messages event
/// This event is used for both bans and timeouts, but doesn't provide duration info
pub struct TwitchModerationEvent<'a> {
    payload: &'a ChannelChatClearUserMessagesV1Payload,
}

impl<'a> TwitchModerationEvent<'a> {
    pub fn new(payload: &'a ChannelChatClearUserMessagesV1Payload) -> Self {
        Self { payload }
    }
}

impl<'a> PlatformModerationEvent for TwitchModerationEvent<'a> {
    fn target_user_id(&self) -> &str {
        self.payload.target_user_id.as_str()
    }

    fn target_username(&self) -> &str {
        self.payload.target_user_name.as_str()
    }

    fn broadcaster_id(&self) -> &str {
        self.payload.broadcaster_user_id.as_str()
    }

    fn is_ban(&self) -> bool {
        // The ChannelChatClearUserMessagesV1 event doesn't distinguish between
        // bans and timeouts, so we treat all as bans for now.
        // Proper distinction would require subscribing to specific ban/timeout events.
        true
    }

    fn duration(&self) -> Option<chrono::Duration> {
        // This event doesn't provide duration information
        None
    }

    fn reason(&self) -> Option<&str> {
        // This event doesn't provide reason information
        None
    }

    fn platform(&self) -> AccountPlatform {
        AccountPlatform::Twitch
    }
}
