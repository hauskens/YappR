/// Channel-specific user roles
/// Note: This is stored as String in the database, not an enum type
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
pub enum ChannelRole {
    Owner,
    Mod,
    Vip,
    Subscriber,
    Follower,
    Basic,
}

impl ChannelRole {
    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "Owner" => Some(Self::Owner),
            "Mod" => Some(Self::Mod),
            "VIP" => Some(Self::Vip),
            "Subscriber" => Some(Self::Subscriber),
            "Follower" => Some(Self::Follower),
            "Basic" => Some(Self::Basic),
            _ => None,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Owner => "Owner",
            Self::Mod => "Mod",
            Self::Vip => "VIP",
            Self::Subscriber => "Subscriber",
            Self::Follower => "Follower",
            Self::Basic => "Basic",
        }
    }

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

    /// Check if this role has at least the specified minimum role level
    pub fn has_minimum_role(&self, minimum: &ChannelRole) -> bool {
        self.priority() >= minimum.priority()
    }
}
