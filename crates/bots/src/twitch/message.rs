use crate::core::PlatformMessage;
use hex_color::HexColor;
use std::{collections::HashMap, str::FromStr};
use twitch_api::eventsub::channel::chat::ChannelChatMessageV1Payload;
use yappr_shared::models::platforms::AccountPlatform;

/// Wrapper around Twitch's EventSub message payload
pub struct TwitchMessage<'a> {
    payload: &'a ChannelChatMessageV1Payload,
    timestamp: chrono::NaiveDateTime,
}

impl<'a> TwitchMessage<'a> {
    pub fn new(payload: &'a ChannelChatMessageV1Payload) -> Self {
        Self {
            payload,
            timestamp: chrono::Utc::now().naive_utc(),
        }
    }
}

impl<'a> PlatformMessage for TwitchMessage<'a> {
    fn user_id(&self) -> &str {
        self.payload.chatter_user_id.as_str()
    }

    fn username(&self) -> &str {
        self.payload.chatter_user_name.as_str()
    }

    fn user_color(&self) -> Option<HexColor> {
        HexColor::from_str(self.payload.color.as_str()).ok()
    }

    fn message_text(&self) -> &str {
        &self.payload.message.text
    }

    fn timestamp(&self) -> chrono::NaiveDateTime {
        self.timestamp
    }

    fn broadcaster_id(&self) -> &str {
        self.payload.broadcaster_user_id.as_str()
    }

    fn extract_badges(&self) -> HashMap<String, String> {
        self.payload
            .badges
            .iter()
            .map(|badge| (badge.set_id.to_string(), badge.id.to_string()))
            .collect()
    }

    fn platform(&self) -> AccountPlatform {
        AccountPlatform::Twitch
    }

    fn avatar_url(&self) -> Option<&str> {
        // Twitch profile images are available at https://static-cdn.jtvnw.net/user-default-pictures/<user_id>-<size>.jpg
        // We'll let the caller handle the actual URL construction if needed
        None
    }
}
