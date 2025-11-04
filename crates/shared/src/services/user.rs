use crate::entities::sea_orm_active_enums::Accountsource;
use crate::entities::{prelude::*, users};
use sea_orm::{
    ActiveModelTrait, ColumnTrait, DatabaseConnection, DbErr, EntityTrait, QueryFilter, Set,
};
use tracing::{info, instrument};

/// Service for managing users
pub struct UserService;

impl UserService {
    /// Get user by ID
    #[instrument(level = "info", skip(db))]
    pub async fn get_user_by_id(
        db: &DatabaseConnection,
        user_id: i32,
    ) -> Result<Option<users::Model>, DbErr> {
        info!(user_id = user_id, "Fetching user by ID");

        let user = Users::find_by_id(user_id).one(db).await?;

        match &user {
            Some(u) => info!(user_id = user_id, username = u.name, "User found"),
            None => info!(user_id = user_id, "User not found"),
        }

        Ok(user)
    }

    /// Get user by external account ID and account type
    #[instrument(level = "info", skip(db))]
    pub async fn get_user_by_external_id(
        db: &DatabaseConnection,
        external_account_id: &str,
        account_type: Accountsource,
    ) -> Result<Option<users::Model>, DbErr> {
        let account_type_str = format!("{:?}", account_type);

        info!(
            external_account_id = external_account_id,
            account_type = account_type_str,
            "Fetching user by external account ID"
        );

        let user = Users::find()
            .filter(users::Column::ExternalAccountId.eq(external_account_id))
            .filter(users::Column::AccountType.eq(account_type))
            .one(db)
            .await?;

        match &user {
            Some(u) => info!(user_id = u.id, username = u.name, "User found"),
            None => info!(
                external_account_id = external_account_id,
                account_type = account_type_str,
                "User not found"
            ),
        }

        Ok(user)
    }

    /// Get or create user by external account ID
    /// Consolidates logic from bot files to eliminate duplication
    /// Updates name and color if user already exists
    #[instrument(level = "info", skip(db))]
    pub async fn get_or_create_user(
        db: &DatabaseConnection,
        external_account_id: &str,
        username: &str,
        account_type: Accountsource,
        color: Option<&str>,
        avatar_url: Option<&str>,
    ) -> Result<users::Model, DbErr> {
        let account_type_str = format!("{:?}", account_type);

        info!(
            external_account_id = external_account_id,
            username = username,
            account_type = account_type_str,
            "Getting or creating user"
        );

        // Try to find existing user
        // Clone account_type for the call since it will be consumed
        if let Some(user) =
            Self::get_user_by_external_id(db, external_account_id, account_type.clone()).await?
        {
            // Check if we need to update name, color, or avatar
            let needs_update = user.name != username
                || user.color.as_deref() != color
                || user.avatar_url.as_deref() != avatar_url;

            if needs_update {
                info!(
                    user_id = user.id,
                    old_name = user.name,
                    new_name = username,
                    "Updating user information"
                );

                let mut active: users::ActiveModel = user.into();
                active.name = Set(username.to_string());
                active.color = Set(color.map(|s| s.to_string()));
                active.avatar_url = Set(avatar_url.map(|s| s.to_string()));
                return active.update(db).await;
            }

            return Ok(user);
        }

        // Create new user
        info!(
            external_account_id = external_account_id,
            username = username,
            account_type = ?account_type,
            "Creating new user"
        );

        let new_user = users::ActiveModel {
            name: Set(username.to_string()),
            external_account_id: Set(external_account_id.to_string()),
            account_type: Set(account_type),
            color: Set(color.map(|s| s.to_string())),
            avatar_url: Set(avatar_url.map(|s| s.to_string())),
            disabled: Set(false),
            banned: Set(false),
            globally_banned: Set(false),
            ignore_weight_penalty: Set(false),
            ..Default::default()
        };

        let user = new_user.insert(db).await?;
        info!(user_id = user.id, username = username, "Created new user");
        Ok(user)
    }

    /// Create a new user
    #[instrument(level = "info", skip(db))]
    pub async fn create_user(
        db: &DatabaseConnection,
        external_account_id: &str,
        username: &str,
        account_type: Accountsource,
        color: Option<&str>,
        avatar_url: Option<&str>,
    ) -> Result<users::Model, DbErr> {
        info!(
            external_account_id = external_account_id,
            username = username,
            account_type = ?account_type,
            "Creating user"
        );

        let new_user = users::ActiveModel {
            name: Set(username.to_string()),
            external_account_id: Set(external_account_id.to_string()),
            account_type: Set(account_type),
            color: Set(color.map(|s| s.to_string())),
            avatar_url: Set(avatar_url.map(|s| s.to_string())),
            disabled: Set(false),
            banned: Set(false),
            globally_banned: Set(false),
            ignore_weight_penalty: Set(false),
            ..Default::default()
        };

        new_user.insert(db).await
    }

    /// Update user details (name, color, avatar)
    #[instrument(level = "info", skip(db))]
    pub async fn update_user(
        db: &DatabaseConnection,
        user: users::Model,
        name: Option<&str>,
        color: Option<&str>,
        avatar_url: Option<&str>,
    ) -> Result<users::Model, DbErr> {
        info!(user_id = user.id, "Updating user");

        let mut active: users::ActiveModel = user.into();

        if let Some(name) = name {
            active.name = Set(name.to_string());
        }
        if let Some(color) = color {
            active.color = Set(Some(color.to_string()));
        }
        if let Some(avatar_url) = avatar_url {
            active.avatar_url = Set(Some(avatar_url.to_string()));
        }

        active.update(db).await
    }

    /// Update user's last login timestamp
    #[instrument(level = "info", skip(db))]
    pub async fn update_last_login(
        db: &DatabaseConnection,
        user: users::Model,
    ) -> Result<users::Model, DbErr> {
        info!(user_id = user.id, "Updating last login");

        let mut active: users::ActiveModel = user.into();
        active.last_login = Set(Some(chrono::Utc::now().naive_utc()));
        active.update(db).await
    }

    /// Ban user (sets banned flag and optionally reason)
    #[instrument(level = "info", skip(db))]
    pub async fn ban_user(
        db: &DatabaseConnection,
        user: users::Model,
        reason: Option<&str>,
    ) -> Result<users::Model, DbErr> {
        info!(user_id = user.id, reason = ?reason, "Banning user");

        let mut active: users::ActiveModel = user.into();
        active.banned = Set(true);
        active.banned_reason = Set(reason.map(|s| s.to_string()));
        active.update(db).await
    }

    /// Unban user (clears banned flag and reason)
    #[instrument(level = "info", skip(db))]
    pub async fn unban_user(
        db: &DatabaseConnection,
        user: users::Model,
    ) -> Result<users::Model, DbErr> {
        info!(user_id = user.id, "Unbanning user");

        let mut active: users::ActiveModel = user.into();
        active.banned = Set(false);
        active.banned_reason = Set(None);
        active.update(db).await
    }

    /// Globally ban user
    #[instrument(level = "info", skip(db))]
    pub async fn globally_ban_user(
        db: &DatabaseConnection,
        user: users::Model,
        reason: &str,
        expires_at: Option<chrono::NaiveDateTime>,
    ) -> Result<users::Model, DbErr> {
        info!(
            user_id = user.id,
            reason = reason,
            expires_at = ?expires_at,
            "Globally banning user"
        );

        let mut active: users::ActiveModel = user.into();
        active.globally_banned = Set(true);
        active.global_ban_reason = Set(Some(reason.to_string()));
        active.global_ban_expires_at = Set(expires_at);
        active.update(db).await
    }

    /// Globally unban user
    #[instrument(level = "info", skip(db))]
    pub async fn globally_unban_user(
        db: &DatabaseConnection,
        user: users::Model,
    ) -> Result<users::Model, DbErr> {
        info!(user_id = user.id, "Globally unbanning user");

        let mut active: users::ActiveModel = user.into();
        active.globally_banned = Set(false);
        active.global_ban_reason = Set(None);
        active.global_ban_expires_at = Set(None);
        active.update(db).await
    }

    /// Disable user account
    #[instrument(level = "info", skip(db))]
    pub async fn disable_user(
        db: &DatabaseConnection,
        user: users::Model,
    ) -> Result<users::Model, DbErr> {
        info!(user_id = user.id, "Disabling user");

        let mut active: users::ActiveModel = user.into();
        active.disabled = Set(true);
        active.update(db).await
    }

    /// Enable user account
    #[instrument(level = "info", skip(db))]
    pub async fn enable_user(
        db: &DatabaseConnection,
        user: users::Model,
    ) -> Result<users::Model, DbErr> {
        info!(user_id = user.id, "Enabling user");

        let mut active: users::ActiveModel = user.into();
        active.disabled = Set(false);
        active.update(db).await
    }
}
