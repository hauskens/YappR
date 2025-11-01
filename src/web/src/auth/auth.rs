#[cfg(feature = "ssr")]
use axum_login::{AuthUser, AuthnBackend, UserId};
#[cfg(feature = "ssr")]
use sea_orm::{DatabaseConnection, EntityTrait};
#[cfg(feature = "ssr")]
use std::sync::Arc;
#[cfg(feature = "ssr")]
use yappr_shared::entities::prelude::*;

// Wrapper type to avoid orphan rule
#[cfg(feature = "ssr")]
#[derive(Debug, Clone)]
pub struct User(pub yappr_shared::entities::users::Model, pub Vec<u8>);

// Implement AuthUser for our wrapper type
#[cfg(feature = "ssr")]
impl AuthUser for User {
    type Id = i32;

    fn id(&self) -> Self::Id {
        self.0.id
    }

    fn session_auth_hash(&self) -> &[u8] {
        // Use HMAC-SHA256 hash of user_id for session validation
        &self.1
    }
}

#[cfg(feature = "ssr")]
impl User {
    /// Create a new User with computed session hash
    pub fn new(model: yappr_shared::entities::users::Model, secret: &str) -> Self {
        use hmac::{Hmac, Mac};
        use sha2::Sha256;

        type HmacSha256 = Hmac<Sha256>;

        // Create HMAC-SHA256 of user ID with session secret
        let mut mac =
            HmacSha256::new_from_slice(secret.as_bytes()).expect("HMAC can take key of any size");
        mac.update(model.id.to_string().as_bytes());
        let session_hash = mac.finalize().into_bytes().to_vec();

        User(model, session_hash)
    }
}

// Authentication backend
#[cfg(feature = "ssr")]
#[derive(Debug, Clone)]
pub struct Backend {
    pub db: Arc<DatabaseConnection>,
    pub session_secret: String,
}

#[cfg(feature = "ssr")]
impl Backend {
    pub fn new(db: Arc<DatabaseConnection>, session_secret: String) -> Self {
        Self { db, session_secret }
    }
}

#[cfg(feature = "ssr")]
impl AuthnBackend for Backend {
    type User = User;
    type Credentials = ();
    type Error = sea_orm::DbErr;

    async fn authenticate(
        &self,
        _creds: Self::Credentials,
    ) -> Result<Option<Self::User>, Self::Error> { Ok(None) }

    fn get_user(
        &self,
        user_id: &UserId<Self>,
    ) -> impl std::future::Future<Output = Result<Option<Self::User>, Self::Error>> + Send {
        let db = self.db.clone();
        let session_secret = self.session_secret.clone();
        let user_id = *user_id;

        async move {
            let user = Users::find_by_id(user_id).one(db.as_ref()).await?;

            Ok(user.map(|u| User::new(u, &session_secret)))
        }
    }
}

// Type alias for our auth session
#[cfg(feature = "ssr")]
pub type AuthSession = axum_login::AuthSession<Backend>;

// OAuth user creation and management
#[cfg(feature = "ssr")]
pub async fn find_or_create_oauth_user(
    db: Arc<DatabaseConnection>,
    provider: crate::auth::oauth_clients::OAuthProvider,
    profile: &crate::auth::oauth_profile::OAuthUserProfile,
    access_token: &str,
    refresh_token: Option<&str>,
    expires_in: Option<std::time::Duration>,
    session_secret: &str,
) -> Result<User, sea_orm::DbErr> {
    use sea_orm::{ActiveModelTrait, ColumnTrait, EntityTrait, QueryFilter, Set};
    use yappr_shared::entities::{flask_dance_oauth, sea_orm_active_enums::Accountsource, users};

    // First, check if we have an OAuth record for this provider/provider_user_id
    let oauth_record = flask_dance_oauth::Entity::find()
        .filter(flask_dance_oauth::Column::Provider.eq(provider.as_str()))
        .filter(flask_dance_oauth::Column::ProviderUserId.eq(&profile.provider_user_id))
        .one(db.as_ref())
        .await?;

    let user_id = if let Some(oauth_rec) = oauth_record {
        // OAuth record exists, update the token
        let user_id = oauth_rec.user_id;
        let mut active_oauth: flask_dance_oauth::ActiveModel = oauth_rec.into();

        let mut token_json = serde_json::json!({
            "access_token": access_token,
        });

        if let Some(refresh) = refresh_token {
            token_json["refresh_token"] = serde_json::Value::String(refresh.to_string());
        }

        if let Some(expires) = expires_in {
            token_json["expires_in"] = serde_json::Value::Number(expires.as_secs().into());
        }

        active_oauth.token = Set(token_json);
        active_oauth.update(db.as_ref()).await?;

        user_id
    } else {
        // No OAuth record exists, check if user exists by external_account_id
        let account_type = match provider {
            crate::auth::oauth_clients::OAuthProvider::Discord => Accountsource::Discord,
            crate::auth::oauth_clients::OAuthProvider::Twitch => Accountsource::Twitch,
        };

        let existing_user = Users::find()
            .filter(users::Column::ExternalAccountId.eq(&profile.provider_user_id))
            .filter(users::Column::AccountType.eq(account_type.clone()))
            .one(db.as_ref())
            .await?;

        let user_id = if let Some(user) = existing_user {
            // User exists, update their info
            let mut active_user: users::ActiveModel = user.into();
            active_user.name = Set(profile.username.clone());
            active_user.avatar_url = Set(profile.avatar_url.clone());
            active_user.last_login = Set(Some(chrono::Utc::now().naive_utc()));
            let updated_user = active_user.update(db.as_ref()).await?;
            updated_user.id
        } else {
            // Create new user
            let new_user = users::ActiveModel {
                name: Set(profile.username.clone()),
                external_account_id: Set(profile.provider_user_id.clone()),
                account_type: Set(account_type),
                last_login: Set(Some(chrono::Utc::now().naive_utc())),
                avatar_url: Set(profile.avatar_url.clone()),
                banned: Set(false),
                globally_banned: Set(false),
                disabled: Set(false),
                ignore_weight_penalty: Set(false),
                ..Default::default()
            };
            let user = new_user.insert(db.as_ref()).await?;
            user.id
        };

        // Create OAuth record
        let mut token_json = serde_json::json!({
            "access_token": access_token,
        });

        if let Some(refresh) = refresh_token {
            token_json["refresh_token"] = serde_json::Value::String(refresh.to_string());
        }

        if let Some(expires) = expires_in {
            token_json["expires_in"] = serde_json::Value::Number(expires.as_secs().into());
        }

        let new_oauth = flask_dance_oauth::ActiveModel {
            user_id: Set(user_id),
            provider: Set(provider.as_str().to_string()),
            created_at: Set(chrono::Utc::now().naive_utc()),
            token: Set(token_json),
            provider_user_id: Set(profile.provider_user_id.clone()),
            ..Default::default()
        };
        new_oauth.insert(db.as_ref()).await?;

        user_id
    };

    // Fetch and return the user
    let user = Users::find_by_id(user_id)
        .one(db.as_ref())
        .await?
        .ok_or_else(|| {
            sea_orm::DbErr::RecordNotFound("User not found after creation".to_string())
        })?;

    Ok(User::new(user, session_secret))
}
