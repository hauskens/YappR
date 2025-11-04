#[cfg(feature = "database")]
use crate::entities::{
    channels, content_queue_submissions, moderation_actions, permissions, prelude::*,
    user_channel_roles, user_weights, users,
};
use crate::models::enums::ChannelRole;
use async_trait::async_trait;
#[cfg(feature = "database")]
use sea_orm::{
    ActiveModelTrait, ColumnTrait, DatabaseConnection, DbErr, EntityTrait, QueryFilter, Set,
};
use std::str::FromStr;

/// Extension trait for user business logic
pub trait User {
    /// Check if user is banned (any type of ban)
    fn is_banned(&self) -> bool;

    /// Check if user is globally banned
    fn is_globally_banned(&self) -> bool;

    /// Check if user account is disabled
    fn is_disabled(&self) -> bool;

    /// Check if user is active (not banned, not disabled)
    fn is_active(&self) -> bool;
}

/// Extension trait for user database operations
#[cfg(feature = "database")]
#[async_trait]
pub trait UserExt {
    /// Get all global permissions for this user
    async fn get_permissions(
        &self,
        db: &DatabaseConnection,
    ) -> Result<Vec<permissions::Model>, DbErr>;

    /// Get all active channel roles for this user
    async fn get_channel_roles(
        &self,
        db: &DatabaseConnection,
    ) -> Result<Vec<user_channel_roles::Model>, DbErr>;

    /// Get all weights for this user across all broadcasters
    async fn get_weights(&self, db: &DatabaseConnection)
    -> Result<Vec<user_weights::Model>, DbErr>;

    /// Get weight for a specific broadcaster (returns 1.0 if not set)
    async fn get_weight_for_broadcaster(
        &self,
        db: &DatabaseConnection,
        broadcaster_id: i32,
    ) -> Result<f64, DbErr>;

    /// Get all moderation actions targeting this user
    async fn get_moderation_actions_received(
        &self,
        db: &DatabaseConnection,
    ) -> Result<Vec<moderation_actions::Model>, DbErr>;

    /// Get all moderation actions issued by this user
    async fn get_moderation_actions_issued(
        &self,
        db: &DatabaseConnection,
    ) -> Result<Vec<moderation_actions::Model>, DbErr>;

    /// Get all content queue submissions by this user
    async fn get_submissions(
        &self,
        db: &DatabaseConnection,
    ) -> Result<Vec<content_queue_submissions::Model>, DbErr>;

    /// Get the broadcaster_id if this user owns any channels
    /// Mimics the Python property from app/models/user.py:85-100
    async fn get_broadcaster_id(&self, db: &DatabaseConnection) -> Result<Option<i32>, DbErr>;

    /// Get user's role for a specific channel
    async fn get_role_for_channel(
        &self,
        db: &DatabaseConnection,
        channel_id: i32,
    ) -> Result<Option<ChannelRole>, DbErr>;

    /// Check if user is banned by a specific broadcaster
    async fn is_banned_by_broadcaster(
        &self,
        db: &DatabaseConnection,
        broadcaster_id: i32,
    ) -> Result<bool, DbErr>;
    async fn update_role(
        &self,
        db: &DatabaseConnection,
        channel_id: i32,
        role: &ChannelRole,
    ) -> Result<(), DbErr>;
}

impl User for users::Model {
    fn is_banned(&self) -> bool {
        self.banned || self.globally_banned
    }

    fn is_globally_banned(&self) -> bool {
        self.globally_banned
    }

    fn is_disabled(&self) -> bool {
        self.disabled
    }

    fn is_active(&self) -> bool {
        !self.is_banned() && !self.is_disabled()
    }
}

#[cfg(feature = "database")]
#[async_trait]
impl UserExt for users::Model {
    async fn get_permissions(
        &self,
        db: &DatabaseConnection,
    ) -> Result<Vec<permissions::Model>, DbErr> {
        Permissions::find()
            .filter(permissions::Column::UserId.eq(self.id))
            .all(db)
            .await
    }

    async fn get_channel_roles(
        &self,
        db: &DatabaseConnection,
    ) -> Result<Vec<user_channel_roles::Model>, DbErr> {
        UserChannelRoles::find()
            .filter(user_channel_roles::Column::UserId.eq(self.id))
            .filter(user_channel_roles::Column::Active.eq(true))
            .all(db)
            .await
    }

    async fn get_weights(
        &self,
        db: &DatabaseConnection,
    ) -> Result<Vec<user_weights::Model>, DbErr> {
        UserWeights::find()
            .filter(user_weights::Column::UserId.eq(self.id))
            .all(db)
            .await
    }

    async fn get_weight_for_broadcaster(
        &self,
        db: &DatabaseConnection,
        broadcaster_id: i32,
    ) -> Result<f64, DbErr> {
        let weight = UserWeights::find()
            .filter(user_weights::Column::UserId.eq(self.id))
            .filter(user_weights::Column::BroadcasterId.eq(broadcaster_id))
            .one(db)
            .await?
            .map(|w| w.weight)
            .unwrap_or(1.0);

        Ok(weight)
    }

    async fn get_moderation_actions_received(
        &self,
        db: &DatabaseConnection,
    ) -> Result<Vec<moderation_actions::Model>, DbErr> {
        ModerationActions::find()
            .filter(moderation_actions::Column::TargetUserId.eq(self.id))
            .all(db)
            .await
    }

    async fn get_moderation_actions_issued(
        &self,
        db: &DatabaseConnection,
    ) -> Result<Vec<moderation_actions::Model>, DbErr> {
        ModerationActions::find()
            .filter(moderation_actions::Column::IssuedBy.eq(self.id))
            .all(db)
            .await
    }

    async fn get_submissions(
        &self,
        db: &DatabaseConnection,
    ) -> Result<Vec<content_queue_submissions::Model>, DbErr> {
        ContentQueueSubmissions::find()
            .filter(content_queue_submissions::Column::UserId.eq(self.id))
            .all(db)
            .await
    }

    async fn get_broadcaster_id(&self, db: &DatabaseConnection) -> Result<Option<i32>, DbErr> {
        // Check if user's external_account_id matches any channel's platform_channel_id
        let result = Channels::find()
            .filter(channels::Column::PlatformChannelId.eq(&self.external_account_id))
            .find_also_related(Broadcaster)
            .one(db)
            .await?
            .and_then(|(_, broadcaster)| broadcaster)
            .map(|b| b.id);

        Ok(result)
    }

    async fn get_role_for_channel(
        &self,
        db: &DatabaseConnection,
        channel_id: i32,
    ) -> Result<Option<ChannelRole>, DbErr> {
        let role = UserChannelRoles::find()
            .filter(user_channel_roles::Column::UserId.eq(self.id))
            .filter(user_channel_roles::Column::ChannelId.eq(channel_id))
            .filter(user_channel_roles::Column::Active.eq(true))
            .one(db)
            .await?;

        match role {
            Some(r) => Ok(ChannelRole::from_str(&r.role).ok()),
            None => Ok(None),
        }
    }

    async fn is_banned_by_broadcaster(
        &self,
        db: &DatabaseConnection,
        broadcaster_id: i32,
    ) -> Result<bool, DbErr> {
        let weight = UserWeights::find()
            .filter(user_weights::Column::UserId.eq(self.id))
            .filter(user_weights::Column::BroadcasterId.eq(broadcaster_id))
            .one(db)
            .await?;

        Ok(weight.map(|w| w.banned).unwrap_or(false))
    }

    async fn update_role(
        &self,
        db: &DatabaseConnection,
        channel_id: i32,
        role: &ChannelRole,
    ) -> Result<(), DbErr> {
        let user_channel_role = UserChannelRoles::find()
            .filter(user_channel_roles::Column::UserId.eq(self.id))
            .filter(user_channel_roles::Column::ChannelId.eq(channel_id))
            .filter(user_channel_roles::Column::Active.eq(true))
            .one(db)
            .await?;

        match user_channel_role {
            Some(record) => {
                // Update existing role
                let mut active_model: user_channel_roles::ActiveModel = record.into();
                active_model.role = Set(role.to_string());
                active_model.update(db).await?;
                Ok(())
            }
            None => {
                // Create new role
                let new_role = user_channel_roles::ActiveModel {
                    user_id: Set(self.id),
                    channel_id: Set(channel_id),
                    role: Set(role.to_string()),
                    granted_at: Set(chrono::Utc::now().naive_utc()),
                    granted_by: Set(None),
                    active: Set(true),
                    expires_at: Set(None),
                    ..Default::default()
                };
                new_role.insert(db).await?;
                Ok(())
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::entities::sea_orm_active_enums::Accountsource;

    fn create_test_user(
        id: i32,
        name: &str,
        external_id: &str,
        banned: bool,
        globally_banned: bool,
        disabled: bool,
    ) -> users::Model {
        users::Model {
            id,
            name: name.to_string(),
            external_account_id: external_id.to_string(),
            account_type: Accountsource::Twitch,
            last_login: None,
            avatar_url: None,
            banned_reason: None,
            banned,
            globally_banned,
            global_ban_reason: None,
            global_ban_expires_at: None,
            disabled,
            ignore_weight_penalty: false,
            color: None,
        }
    }

    #[test]
    fn test_user_is_banned() {
        let user = create_test_user(1, "test", "123", true, false, false);
        assert!(user.is_banned());
        assert!(!user.is_active());
    }

    #[test]
    fn test_user_is_globally_banned() {
        let user = create_test_user(1, "test", "123", false, true, false);
        assert!(user.is_banned());
        assert!(user.is_globally_banned());
        assert!(!user.is_active());
    }

    #[test]
    fn test_user_is_disabled() {
        let user = create_test_user(1, "test", "123", false, false, true);
        assert!(user.is_disabled());
        assert!(!user.is_active());
    }

    #[test]
    fn test_user_is_active() {
        let user = create_test_user(1, "test", "123", false, false, false);
        assert!(user.is_active());
        assert!(!user.is_banned());
        assert!(!user.is_disabled());
    }
}
