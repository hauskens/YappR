use crate::entities::{moderation_actions, prelude::*, users};
use chrono::{Duration, Utc};
use sea_orm::{
    ActiveModelTrait, ColumnTrait, DatabaseConnection, DbErr, EntityTrait, QueryFilter, Set,
};
use tracing::{info, instrument};

/// Moderation action types
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ModerationType {
    Ban,
    Timeout,
    Warning,
}

impl ModerationType {
    pub fn as_str(&self) -> &'static str {
        match self {
            ModerationType::Ban => "ban",
            ModerationType::Timeout => "timeout",
            ModerationType::Warning => "warning",
        }
    }
}

/// Moderation scope
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ModerationScope {
    Global,
    Channel,
}

impl ModerationScope {
    pub fn as_str(&self) -> &'static str {
        match self {
            ModerationScope::Global => "global",
            ModerationScope::Channel => "channel",
        }
    }
}

/// Service for moderation operations
pub struct ModerationService;

impl ModerationService {
    /// Ban a user globally or from a specific channel
    ///
    /// # Arguments
    /// * `db` - Database connection
    /// * `target_user_id` - ID of user to ban
    /// * `scope` - Ban scope (Global or Channel)
    /// * `reason` - Reason for the ban
    /// * `issued_by_user_id` - ID of moderator issuing the ban
    /// * `channel_id` - Channel ID (required for channel-specific bans)
    /// * `duration_seconds` - Optional duration in seconds (None = permanent)
    #[instrument(level = "info", skip(db))]
    pub async fn ban_user(
        db: &DatabaseConnection,
        target_user_id: i32,
        scope: ModerationScope,
        reason: String,
        issued_by_user_id: i32,
        channel_id: Option<i32>,
        duration_seconds: Option<i32>,
    ) -> Result<moderation_actions::Model, DbErr> {
        info!(
            target_user_id = target_user_id,
            scope = ?scope,
            reason = %reason,
            issued_by = issued_by_user_id,
            "Banning user"
        );

        // Calculate expiration time if duration provided
        let expires_at =
            duration_seconds.map(|dur| (Utc::now() + Duration::seconds(dur as i64)).naive_utc());

        // Create moderation action
        let action = moderation_actions::ActiveModel {
            target_user_id: Set(target_user_id),
            action_type: Set(ModerationType::Ban.as_str().to_string()),
            scope: Set(scope.as_str().to_string()),
            channel_id: Set(channel_id),
            reason: Set(reason.clone()),
            duration_seconds: Set(duration_seconds),
            expires_at: Set(expires_at),
            issued_by: Set(Some(issued_by_user_id)),
            issued_at: Set(Utc::now().naive_utc()),
            active: Set(true),
            ..Default::default()
        };

        let inserted_action = action.insert(db).await?;

        // Update user's global ban status if global scope
        if matches!(scope, ModerationScope::Global) {
            let user =
                Users::find_by_id(target_user_id)
                    .one(db)
                    .await?
                    .ok_or(DbErr::RecordNotFound(format!(
                        "User {} not found",
                        target_user_id
                    )))?;

            let mut user_active: users::ActiveModel = user.into();
            user_active.globally_banned = Set(true);
            user_active.global_ban_reason = Set(Some(reason.clone()));
            user_active.global_ban_expires_at = Set(expires_at);
            user_active.update(db).await?;
        }

        info!(action_id = inserted_action.id, "User banned successfully");

        Ok(inserted_action)
    }

    /// Unban a user
    #[instrument(level = "info", skip(db))]
    pub async fn unban_user(
        db: &DatabaseConnection,
        target_user_id: i32,
        scope: ModerationScope,
        channel_id: Option<i32>,
    ) -> Result<(), DbErr> {
        info!(
            target_user_id = target_user_id,
            scope = ?scope,
            "Unbanning user"
        );

        // Delete active ban actions
        let mut query = ModerationActions::delete_many()
            .filter(moderation_actions::Column::TargetUserId.eq(target_user_id))
            .filter(moderation_actions::Column::ActionType.eq(ModerationType::Ban.as_str()))
            .filter(moderation_actions::Column::Scope.eq(scope.as_str()));

        if let Some(ch_id) = channel_id {
            query = query.filter(moderation_actions::Column::ChannelId.eq(ch_id));
        }

        query.exec(db).await?;

        // Update user's global ban status if global scope
        if matches!(scope, ModerationScope::Global)
            && let Some(user) = Users::find_by_id(target_user_id).one(db).await?
        {
            let mut user_active: users::ActiveModel = user.into();
            user_active.globally_banned = Set(false);
            user_active.global_ban_reason = Set(None);
            user_active.global_ban_expires_at = Set(None);
            user_active.update(db).await?;
        }

        info!("User unbanned successfully");
        Ok(())
    }

    /// Timeout a user in a specific channel
    #[instrument(level = "info", skip(db))]
    pub async fn timeout_user(
        db: &DatabaseConnection,
        target_user_id: i32,
        channel_id: i32,
        reason: String,
        issued_by_user_id: i32,
        duration_seconds: i32,
    ) -> Result<moderation_actions::Model, DbErr> {
        info!(
            target_user_id = target_user_id,
            channel_id = channel_id,
            duration_seconds = duration_seconds,
            "Timing out user"
        );

        let expires_at = (Utc::now() + Duration::seconds(duration_seconds as i64)).naive_utc();

        let action = moderation_actions::ActiveModel {
            target_user_id: Set(target_user_id),
            action_type: Set(ModerationType::Timeout.as_str().to_string()),
            scope: Set(ModerationScope::Channel.as_str().to_string()),
            channel_id: Set(Some(channel_id)),
            reason: Set(reason),
            duration_seconds: Set(Some(duration_seconds)),
            expires_at: Set(Some(expires_at)),
            issued_by: Set(Some(issued_by_user_id)),
            issued_at: Set(Utc::now().naive_utc()),
            active: Set(true),
            ..Default::default()
        };

        let inserted_action = action.insert(db).await?;

        info!(
            action_id = inserted_action.id,
            "User timed out successfully"
        );

        Ok(inserted_action)
    }

    /// Check if a user is currently banned (globally or in a specific channel)
    #[instrument(level = "info", skip(db))]
    pub async fn is_user_banned(
        db: &DatabaseConnection,
        user_id: i32,
        channel_id: Option<i32>,
    ) -> Result<bool, DbErr> {
        let now = Utc::now();

        // Check global bans
        let global_ban = ModerationActions::find()
            .filter(moderation_actions::Column::TargetUserId.eq(user_id))
            .filter(moderation_actions::Column::ActionType.eq(ModerationType::Ban.as_str()))
            .filter(moderation_actions::Column::Scope.eq(ModerationScope::Global.as_str()))
            .filter(
                moderation_actions::Column::ExpiresAt
                    .is_null()
                    .or(moderation_actions::Column::ExpiresAt.gt(now)),
            )
            .one(db)
            .await?;

        if global_ban.is_some() {
            return Ok(true);
        }

        // Check channel-specific bans if channel_id provided
        if let Some(ch_id) = channel_id {
            let channel_ban = ModerationActions::find()
                .filter(moderation_actions::Column::TargetUserId.eq(user_id))
                .filter(moderation_actions::Column::ActionType.eq(ModerationType::Ban.as_str()))
                .filter(moderation_actions::Column::Scope.eq(ModerationScope::Channel.as_str()))
                .filter(moderation_actions::Column::ChannelId.eq(ch_id))
                .filter(
                    moderation_actions::Column::ExpiresAt
                        .is_null()
                        .or(moderation_actions::Column::ExpiresAt.gt(now)),
                )
                .one(db)
                .await?;

            if channel_ban.is_some() {
                return Ok(true);
            }
        }

        Ok(false)
    }

    /// Check if a user is currently timed out in a specific channel
    #[instrument(level = "info", skip(db))]
    pub async fn is_user_timed_out(
        db: &DatabaseConnection,
        user_id: i32,
        channel_id: i32,
    ) -> Result<bool, DbErr> {
        let now = Utc::now();

        let timeout = ModerationActions::find()
            .filter(moderation_actions::Column::TargetUserId.eq(user_id))
            .filter(moderation_actions::Column::ActionType.eq(ModerationType::Timeout.as_str()))
            .filter(moderation_actions::Column::ChannelId.eq(channel_id))
            .filter(moderation_actions::Column::ExpiresAt.gt(now))
            .one(db)
            .await?;

        Ok(timeout.is_some())
    }

    /// Get all active moderation actions for a user
    #[instrument(level = "info", skip(db))]
    pub async fn get_active_actions_for_user(
        db: &DatabaseConnection,
        user_id: i32,
    ) -> Result<Vec<moderation_actions::Model>, DbErr> {
        let now = Utc::now();

        ModerationActions::find()
            .filter(moderation_actions::Column::TargetUserId.eq(user_id))
            .filter(
                moderation_actions::Column::ExpiresAt
                    .is_null()
                    .or(moderation_actions::Column::ExpiresAt.gt(now)),
            )
            .all(db)
            .await
    }

    /// Clean up expired moderation actions
    #[instrument(level = "info", skip(db))]
    pub async fn cleanup_expired_actions(db: &DatabaseConnection) -> Result<u64, DbErr> {
        let now = Utc::now();

        let result = ModerationActions::delete_many()
            .filter(moderation_actions::Column::ExpiresAt.is_not_null())
            .filter(moderation_actions::Column::ExpiresAt.lte(now))
            .exec(db)
            .await?;

        info!(
            deleted_count = result.rows_affected,
            "Cleaned up expired moderation actions"
        );

        Ok(result.rows_affected)
    }
}
