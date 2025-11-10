use crate::core::PlatformMessage;
use hex_color::HexColor;
use serenity::all::Message;
use std::collections::HashMap;
use yappr_shared::models::platforms::AccountPlatform;

/// Wrapper around Discord's message data with extracted fields
pub struct DiscordMessage {
    user_id: String,
    username: String,
    content: String,
    broadcaster_id: String,
    timestamp: chrono::NaiveDateTime,
    avatar_url: Option<String>,
}

impl DiscordMessage {
    pub fn new(message: Message, broadcaster_id: i32) -> Self {
        let user_id = message.author.id.to_string();
        let broadcaster_id = broadcaster_id.to_string();

        let username = message
            .author
            .global_name
            .as_deref()
            .unwrap_or(&message.author.name)
            .to_string();

        let content = message.content;

        Self {
            user_id,
            username,
            content,
            broadcaster_id,
            timestamp: chrono::Utc::now().naive_utc(),
            avatar_url: message
                .author
                .avatar_url()
                .as_deref()
                .map(|s| s.to_string()),
        }
    }
}

impl PlatformMessage for DiscordMessage {
    fn user_id(&self) -> &str {
        &self.user_id
    }

    fn username(&self) -> &str {
        &self.username
    }

    fn user_color(&self) -> Option<HexColor> {
        // Discord doesn't have per-user colors in the same way Twitch does
        // Users get colors from their highest role, but we'd need guild member data
        // Return None for now
        Some(HexColor::WHITE)
    }

    fn message_text(&self) -> &str {
        &self.content
    }

    fn timestamp(&self) -> chrono::NaiveDateTime {
        self.timestamp
    }

    fn broadcaster_id(&self) -> &str {
        &self.broadcaster_id
    }

    fn extract_badges(&self) -> HashMap<String, String> {
        // Discord uses roles instead of badges
        // We don't have guild member context here to extract roles
        // Roles will be handled separately in Discord-specific code
        HashMap::new()
    }

    fn platform(&self) -> AccountPlatform {
        AccountPlatform::Discord
    }

    fn avatar_url(&self) -> Option<&str> {
        self.avatar_url.as_deref()
    }
}
