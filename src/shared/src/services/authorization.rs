use crate::entities::sea_orm_active_enums::Permissiontype;
use crate::entities::{
    broadcaster, channels, permissions, prelude::*, user_channel_roles, users, video,
};
use crate::models::enums::ChannelRole;
use sea_orm::{ColumnTrait, DatabaseConnection, DbErr, EntityTrait, QueryFilter};
use std::collections::HashMap;
use tracing::{info, instrument, warn};

/// Custom error type for authorization operations
#[derive(Debug)]
pub enum AuthError {
    Database(DbErr),
    Forbidden,
    Banned,
    GloballyBanned,
    Disabled,
    Unauthenticated,
}

impl std::fmt::Display for AuthError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            AuthError::Database(e) => write!(f, "Database error: {}", e),
            AuthError::Forbidden => write!(f, "Access forbidden"),
            AuthError::Banned => write!(f, "User is banned"),
            AuthError::GloballyBanned => write!(f, "User is globally banned"),
            AuthError::Disabled => write!(f, "User account is disabled"),
            AuthError::Unauthenticated => write!(f, "Authentication required"),
        }
    }
}

impl std::error::Error for AuthError {}

impl From<DbErr> for AuthError {
    fn from(err: DbErr) -> Self {
        AuthError::Database(err)
    }
}

/// Authorization context containing user permissions and roles
#[derive(Debug, Clone)]
pub struct AuthContext {
    pub user: Option<users::Model>,
    pub permissions: Vec<permissions::Model>,
    pub channel_roles: HashMap<i32, ChannelRole>, // channel_id -> role
}

impl AuthContext {
    /// Create an unauthenticated context (no user)
    pub fn anonymous() -> Self {
        Self {
            user: None,
            permissions: Vec::new(),
            channel_roles: HashMap::new(),
        }
    }

    /// Load authorization context for a user from the database
    #[instrument(level = "info", skip(db))]
    pub async fn load(db: &DatabaseConnection, user: users::Model) -> Result<Self, AuthError> {
        let user_id = user.id;

        info!(
            user_id = user_id,
            user_name = user.name,
            "Loading auth context"
        );

        // Load global permissions
        let permissions = Permissions::find()
            .filter(permissions::Column::UserId.eq(user_id))
            .all(db)
            .await?;

        info!(
            user_id = user_id,
            permission_count = permissions.len(),
            "Loaded permissions"
        );

        // Load channel roles
        let roles = UserChannelRoles::find()
            .filter(user_channel_roles::Column::UserId.eq(user_id))
            .filter(user_channel_roles::Column::Active.eq(true))
            .all(db)
            .await?;

        // Convert to HashMap with parsed roles
        let mut channel_roles = HashMap::new();
        for role in roles {
            if let Some(channel_role) = ChannelRole::from_str(&role.role) {
                channel_roles.insert(role.channel_id, channel_role);
            } else {
                warn!(
                    user_id = user_id,
                    channel_id = role.channel_id,
                    role_str = role.role,
                    "Unknown channel role"
                );
            }
        }

        info!(
            user_id = user_id,
            channel_role_count = channel_roles.len(),
            "Loaded channel roles"
        );

        Ok(Self {
            user: Some(user),
            permissions,
            channel_roles,
        })
    }

    /// Check if user is authenticated
    pub fn is_authenticated(&self) -> bool {
        self.user.is_some()
    }

    /// Check if user has a specific global permission
    pub fn has_permission(&self, permission: Permissiontype) -> bool {
        self.permissions
            .iter()
            .any(|p| p.permission_type == permission)
    }

    /// Check if user is a global admin
    pub fn is_admin(&self) -> bool {
        self.has_permission(Permissiontype::Admin)
    }

    /// Check if user is a global moderator
    pub fn is_moderator(&self) -> bool {
        self.has_permission(Permissiontype::Moderator)
    }

    /// Check if user is a global reader
    pub fn is_reader(&self) -> bool {
        self.has_permission(Permissiontype::Reader)
    }

    /// Check if user is banned (any type of ban)
    pub fn is_banned(&self) -> bool {
        self.user
            .as_ref()
            .is_some_and(|u| u.banned || u.globally_banned)
    }

    /// Check if user is globally banned
    pub fn is_globally_banned(&self) -> bool {
        self.user.as_ref().is_some_and(|u| u.globally_banned)
    }

    /// Check if user account is disabled
    pub fn is_disabled(&self) -> bool {
        self.user.as_ref().is_some_and(|u| u.disabled)
    }

    /// Get user's role for a specific channel
    pub fn get_channel_role(&self, channel_id: i32) -> Option<&ChannelRole> {
        self.channel_roles.get(&channel_id)
    }

    /// Check if user has a specific role in a channel
    pub fn has_channel_role(&self, channel_id: i32, role: &ChannelRole) -> bool {
        self.get_channel_role(channel_id) == Some(role)
    }

    /// Check if user has at least the minimum role level in a channel
    pub fn has_minimum_channel_role(&self, channel_id: i32, minimum: &ChannelRole) -> bool {
        self.get_channel_role(channel_id)
            .is_some_and(|r| r.has_minimum_role(minimum))
    }

    /// Check if user owns a channel (is broadcaster)
    pub fn is_channel_owner(&self, channel_id: i32) -> bool {
        self.has_channel_role(channel_id, &ChannelRole::Owner)
    }

    /// Check if user is a moderator of a channel
    pub fn is_channel_moderator(&self, channel_id: i32) -> bool {
        self.has_minimum_channel_role(channel_id, &ChannelRole::Mod)
    }

    /// Check if user can view a channel (including hidden channels)
    pub fn can_view_channel(&self, channel: &channels::Model) -> bool {
        // Admins can view all channels
        if self.is_admin() {
            return true;
        }

        // Public channels (not hidden) are visible to everyone
        // Note: We need to check if broadcaster is hidden
        // For now, we'll assume all channels are visible unless we load broadcaster data
        // This should be enhanced to check broadcaster.hidden field

        // Channel owner and mods can view their channels
        if self.is_channel_owner(channel.id) || self.is_channel_moderator(channel.id) {
            return true;
        }

        // For now, allow viewing all channels
        // TODO: Implement broadcaster hidden check
        true
    }

    /// Check if user can edit a channel
    pub fn can_edit_channel(&self, channel: &channels::Model) -> bool {
        // Admins can edit all channels
        if self.is_admin() {
            return true;
        }

        // Channel owner can edit
        if self.is_channel_owner(channel.id) {
            return true;
        }

        false
    }

    /// Check if user can view a broadcaster (including hidden broadcasters)
    pub fn can_view_broadcaster(&self, broadcaster: &broadcaster::Model) -> bool {
        // Admins can view all broadcasters
        if self.is_admin() {
            return true;
        }

        // Public broadcasters are visible to everyone
        if !broadcaster.hidden {
            return true;
        }

        // Check if user owns any channel belonging to this broadcaster
        // This requires loading channels, so we'll need a separate method for that
        // For now, hidden broadcasters are only visible to admins
        false
    }

    /// Check if user can view a video (respecting active status)
    pub fn can_view_video(&self, video: &video::Model, channel: &channels::Model) -> bool {
        // Must be able to view the channel first
        if !self.can_view_channel(channel) {
            return false;
        }

        // Active videos are visible to anyone who can see the channel
        if video.active {
            return true;
        }

        // Inactive videos are only visible to admins and channel mods/owners
        self.is_admin() || self.is_channel_moderator(channel.id)
    }

    /// Filter channels to only those visible to this user
    pub fn filter_visible_channels(&self, channels: Vec<channels::Model>) -> Vec<channels::Model> {
        channels
            .into_iter()
            .filter(|c| self.can_view_channel(c))
            .collect()
    }

    /// Filter broadcasters to only those visible to this user
    pub fn filter_visible_broadcasters(
        &self,
        broadcasters: Vec<broadcaster::Model>,
    ) -> Vec<broadcaster::Model> {
        broadcasters
            .into_iter()
            .filter(|b| self.can_view_broadcaster(b))
            .collect()
    }

    /// Verify user is not banned or disabled, return error if they are
    pub fn verify_active(&self) -> Result<(), AuthError> {
        if let Some(user) = &self.user {
            if user.globally_banned {
                return Err(AuthError::GloballyBanned);
            }
            if user.banned {
                return Err(AuthError::Banned);
            }
            if user.disabled {
                return Err(AuthError::Disabled);
            }
        }
        Ok(())
    }

    /// Require authentication, return error if not authenticated
    pub fn require_auth(&self) -> Result<&users::Model, AuthError> {
        self.user.as_ref().ok_or(AuthError::Unauthenticated)
    }

    /// Require admin permission, return error if not admin
    pub fn require_admin(&self) -> Result<(), AuthError> {
        if !self.is_admin() {
            return Err(AuthError::Forbidden);
        }
        Ok(())
    }

    /// Require channel access with minimum role
    pub fn require_channel_role(
        &self,
        channel_id: i32,
        minimum: &ChannelRole,
    ) -> Result<(), AuthError> {
        if self.is_admin() {
            return Ok(());
        }

        if !self.has_minimum_channel_role(channel_id, minimum) {
            return Err(AuthError::Forbidden);
        }

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_anonymous_context() {
        let auth = AuthContext::anonymous();
        assert!(!auth.is_authenticated());
        assert!(!auth.is_admin());
        assert!(!auth.is_banned());
    }

    #[test]
    fn test_channel_role_priority() {
        assert!(ChannelRole::Owner.priority() > ChannelRole::Mod.priority());
        assert!(ChannelRole::Mod.priority() > ChannelRole::Vip.priority());
        assert!(ChannelRole::Vip.priority() > ChannelRole::Subscriber.priority());
    }

    #[test]
    fn test_minimum_role_check() {
        assert!(ChannelRole::Owner.has_minimum_role(&ChannelRole::Mod));
        assert!(ChannelRole::Mod.has_minimum_role(&ChannelRole::Vip));
        assert!(!ChannelRole::Vip.has_minimum_role(&ChannelRole::Mod));
    }
}
