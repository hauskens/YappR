use crate::models::platforms::BasePlatform;
use strum_macros::{Display, EnumString};

/// Note: This is stored as String in the database, not an enum type
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Display, EnumString)]
pub enum ChannelRole {
    #[strum(to_string = "Owner")]
    Owner,
    #[strum(to_string = "Mod")]
    Mod,
    #[strum(to_string = "VIP")]
    Vip,
    #[strum(to_string = "Subscriber")]
    Subscriber,
    #[strum(to_string = "Follower")]
    Follower,
    #[strum(to_string = "Basic")]
    Basic,
}

impl ChannelRole {
    /// Returns role priority level (higher = more permissions)
    pub fn priority(&self) -> u8 {
        match self {
            Self::Owner => 100,
            Self::Mod => 80,
            Self::Vip => 60,
            Self::Subscriber => 40,
            Self::Follower => 20,
            Self::Basic => 10,
        }
    }

    pub fn description(&self) -> &'static str {
        match self {
            Self::Owner => "Channel owner with full administrative privileges",
            Self::Mod => "Channel moderator with moderation privileges",
            Self::Vip => "VIP member with special privileges",
            Self::Subscriber => "Subscribed member of the channel",
            Self::Follower => "Follower of the channel",
            Self::Basic => "Basic channel member",
        }
    }

    pub fn background_color(&self) -> &'static str {
        match self {
            Self::Owner => "#ff6b6b",      // Red
            Self::Mod => "#4ecdc4",        // Teal
            Self::Vip => "#ffe66d",        // Yellow
            Self::Subscriber => "#a8e6cf", // Light green
            Self::Follower => "#dcedc8",   // Very light green
            Self::Basic => "#f5f5f5",      // Light gray
        }
    }

    pub fn text_color(&self) -> &'static str {
        match self {
            Self::Owner => "#ffffff",      // White
            Self::Mod => "#ffffff",        // White
            Self::Vip => "#2c3e50",        // Dark gray
            Self::Subscriber => "#2c3e50", // Dark gray
            Self::Follower => "#2c3e50",   // Dark gray
            Self::Basic => "#2c3e50",      // Dark gray
        }
    }

    pub fn from_platform_badge(platform: &BasePlatform, badge: &str) -> Option<Self> {
        match platform {
            BasePlatform::YouTube => match badge {
                "owner" => Some(Self::Owner),
                "moderator" => Some(Self::Mod),
                "vip" => Some(Self::Vip),
                "subscriber" => Some(Self::Subscriber),
                "follower" => Some(Self::Follower),
                _ => None,
            },
            BasePlatform::Twitch => match badge {
                "broadcaster" => Some(Self::Owner),
                "moderator" => Some(Self::Mod),
                "vip" => Some(Self::Vip),
                "subscriber" | "founder" => Some(Self::Subscriber),
                "follower" => Some(Self::Follower),
                _ => None,
            },
            _ => None,
        }
    }

    /// Check if this role has at least the specified minimum role level
    pub fn has_minimum_role(&self, minimum: &ChannelRole) -> bool {
        self.priority() >= minimum.priority()
    }
}
