use moka::future::Cache;
use sea_orm::{DatabaseConnection, DbErr};
use std::time::Duration;
use yappr_shared::entities::users;
use yappr_shared::models::enums::ChannelRole;
use yappr_shared::models::platforms::AccountPlatform;
use yappr_shared::models::user::UserExt;
use yappr_shared::services::user::UserService;

/// Service for managing user roles based on User badges
/// Uses shared UserService for common operations
pub struct BotUserService {
    db: DatabaseConnection,
    user_cache: Cache<String, users::Model>,
    platform: AccountPlatform,
}

impl BotUserService {
    pub fn new(db: DatabaseConnection, platform: AccountPlatform) -> Self {
        Self {
            db,
            user_cache: Cache::builder()
                .max_capacity(1000)
                .time_to_live(Duration::from_secs(60 * 5))
                .build(),
            platform,
        }
    }

    pub async fn get_or_create_user(
        &self,
        external_account_id: &str,
        external_account_name: &str,
        color: Option<&str>,
    ) -> Result<users::Model, DbErr> {
        if let Some(user) = self.user_cache.get(external_account_id).await {
            return Ok(user);
        }
        let user = UserService::get_or_create_user(
            &self.db,
            external_account_id,
            external_account_name,
            self.platform,
            color,
            None,
        )
        .await?;
        self.user_cache
            .insert(external_account_id.to_string(), user.clone())
            .await;
        Ok(user)
    }

    pub async fn update_user_role(
        &self,
        user: users::Model,
        channel_id: i32,
        role: &ChannelRole,
    ) -> Result<(), DbErr> {
        user.update_role(&self.db, channel_id, role).await
    }
}
