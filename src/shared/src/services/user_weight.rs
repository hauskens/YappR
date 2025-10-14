use crate::entities::{prelude::*, user_weights};
use sea_orm::{
    ActiveModelTrait, ColumnTrait, DatabaseConnection, DbErr, EntityTrait, QueryFilter, Set,
};
use tracing::{info, instrument};

/// Service for managing per-broadcaster user weights and bans
pub struct UserWeightService;

impl UserWeightService {
    /// Get user's weight for a specific broadcaster (default: 1.0)
    #[instrument(level = "info", skip(db))]
    pub async fn get_weight(
        db: &DatabaseConnection,
        user_id: i32,
        broadcaster_id: i32,
    ) -> Result<f64, DbErr> {
        let weight = UserWeights::find()
            .filter(user_weights::Column::UserId.eq(user_id))
            .filter(user_weights::Column::BroadcasterId.eq(broadcaster_id))
            .one(db)
            .await?
            .map(|w| w.weight)
            .unwrap_or(1.0);

        info!(
            user_id = user_id,
            broadcaster_id = broadcaster_id,
            weight = weight,
            "Retrieved user weight"
        );
        Ok(weight)
    }

    /// Set user's weight (creates if not exists)
    #[instrument(level = "info", skip(db))]
    pub async fn set_weight(
        db: &DatabaseConnection,
        user_id: i32,
        broadcaster_id: i32,
        weight: f64,
    ) -> Result<user_weights::Model, DbErr> {
        info!(
            user_id = user_id,
            broadcaster_id = broadcaster_id,
            weight = weight,
            "Setting user weight"
        );

        // Try to find existing record
        let existing = UserWeights::find()
            .filter(user_weights::Column::UserId.eq(user_id))
            .filter(user_weights::Column::BroadcasterId.eq(broadcaster_id))
            .one(db)
            .await?;

        match existing {
            Some(record) => {
                // Update existing
                let mut active: user_weights::ActiveModel = record.into();
                active.weight = Set(weight);
                active.update(db).await
            }
            None => {
                // Create new
                let active_model = user_weights::ActiveModel {
                    user_id: Set(user_id),
                    broadcaster_id: Set(broadcaster_id),
                    weight: Set(weight),
                    banned: Set(false),
                    banned_at: Set(None),
                    unban_at: Set(None),
                    ..Default::default()
                };
                active_model.insert(db).await
            }
        }
    }

    /// Adjust weight by delta
    #[instrument(level = "info", skip(db))]
    pub async fn adjust_weight(
        db: &DatabaseConnection,
        user_id: i32,
        broadcaster_id: i32,
        delta: f64,
    ) -> Result<f64, DbErr> {
        let current = Self::get_weight(db, user_id, broadcaster_id).await?;
        let new_weight = (current + delta).max(0.0); // Don't allow negative weights
        Self::set_weight(db, user_id, broadcaster_id, new_weight).await?;

        info!(
            user_id = user_id,
            broadcaster_id = broadcaster_id,
            old_weight = current,
            delta = delta,
            new_weight = new_weight,
            "Adjusted user weight"
        );
        Ok(new_weight)
    }

    /// Ban user for this broadcaster
    #[instrument(level = "info", skip(db))]
    pub async fn ban_user(
        db: &DatabaseConnection,
        user_id: i32,
        broadcaster_id: i32,
        unban_at: Option<chrono::NaiveDateTime>,
    ) -> Result<user_weights::Model, DbErr> {
        info!(
            user_id = user_id,
            broadcaster_id = broadcaster_id,
            "Banning user"
        );

        let record = Self::set_weight(db, user_id, broadcaster_id, 0.0).await?;
        let mut active: user_weights::ActiveModel = record.into();
        active.banned = Set(true);
        active.banned_at = Set(Some(chrono::Utc::now().naive_utc()));
        active.unban_at = Set(unban_at);
        active.update(db).await
    }

    /// Unban user
    #[instrument(level = "info", skip(db))]
    pub async fn unban_user(
        db: &DatabaseConnection,
        user_id: i32,
        broadcaster_id: i32,
        restore_weight: f64,
    ) -> Result<user_weights::Model, DbErr> {
        info!(
            user_id = user_id,
            broadcaster_id = broadcaster_id,
            restore_weight = restore_weight,
            "Unbanning user"
        );

        let record = Self::set_weight(db, user_id, broadcaster_id, restore_weight).await?;
        let mut active: user_weights::ActiveModel = record.into();
        active.banned = Set(false);
        active.banned_at = Set(None);
        active.unban_at = Set(None);
        active.update(db).await
    }

    /// Check if user is banned
    #[instrument(level = "info", skip(db))]
    pub async fn is_banned(
        db: &DatabaseConnection,
        user_id: i32,
        broadcaster_id: i32,
    ) -> Result<bool, DbErr> {
        let record = UserWeights::find()
            .filter(user_weights::Column::UserId.eq(user_id))
            .filter(user_weights::Column::BroadcasterId.eq(broadcaster_id))
            .one(db)
            .await?;

        Ok(record.map(|r| r.banned).unwrap_or(false))
    }
}
