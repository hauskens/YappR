use crate::entities::{users, flask_dance_oauth};
use crate::types::OAuthToken;
use sea_orm::*;

#[derive(Debug)]
pub struct UserService {
    db: DatabaseConnection,
}

impl UserService {
    pub fn new(db: DatabaseConnection) -> Self {
        Self { db }
    }

    /// Retrieves all users from the database.
    /// 
    /// # Arguments
    /// 
    /// * `include_hidden` - Optional include hidden users, otherwise excludes hidden users.
    pub async fn get_all(&self) -> Result<Vec<users::Model>, DbErr> {
        let query = users::Entity::find();
        
        let users = query.all(&self.db).await?;
        Ok(users)
    }
    /// Get the bot user
    pub async fn get_bot_user(&self) -> Result<users::Model, DbErr> {
        let bot_oauth = flask_dance_oauth::Entity::find()
            .filter(flask_dance_oauth::Column::Provider.eq("twitch_bot"))
            .one(&self.db)
            .await?
            .unwrap();

        let bot_user = users::Entity::find()
            .filter(users::Column::Id.eq(bot_oauth.user_id))
            .one(&self.db)
            .await?
            .unwrap();
        
        Ok(bot_user)
    }
    /// Get the user by ID
    /// 
    /// # Arguments
    /// 
    /// * `user_id` - The ID of the user to get.
    pub async fn get_user_by_id(&self, user_id: i32) -> Result<users::Model, DbErr> {
        let user = users::Entity::find()
            .filter(users::Column::Id.eq(user_id))
            .one(&self.db)
            .await?
            .unwrap();
        
        Ok(user)
    }
    /// Get the user by external account ID
    /// 
    /// # Arguments
    /// 
    /// * `external_account_id` - The external account ID of the user to get.
    pub async fn get_user_by_external_account_id(&self, external_account_id: &str) -> Result<users::Model, DbErr> {
        let user = users::Entity::find()
            .filter(users::Column::ExternalAccountId.eq(external_account_id))
            .one(&self.db)
            .await?
            .unwrap();
        
        Ok(user)
    }
    /// Get the OAUTH row for a user
    /// 
    /// # Arguments
    /// 
    /// * `user_id` - The ID of the user to get the OAUTH row for.
    pub async fn get_user_oauth_token(&self, user_id: i32) -> Result<Option<OAuthToken>, DbErr> {
        let oauth = flask_dance_oauth::Entity::find()
            .filter(flask_dance_oauth::Column::UserId.eq(user_id))
            .one(&self.db)
            .await?;

        if let Some(oauth) = oauth {
            if OAuthToken::from_json_value(&oauth.token).is_err() {
                return Ok(None);
            }
            Ok(Some(OAuthToken::from_json_value(&oauth.token).unwrap()))
        } else {
            Ok(None)
        }
    }
    
    /// Update OAuth token for a user
    pub async fn update_user_oauth_token(&self, user_id: i32, oauth_token: &OAuthToken) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        use sea_orm::ActiveValue::Set;
        
        let oauth_record = flask_dance_oauth::Entity::find()
            .filter(flask_dance_oauth::Column::UserId.eq(user_id))
            .one(&self.db)
            .await?;
            
        if let Some(oauth) = oauth_record {
            let mut oauth_active: flask_dance_oauth::ActiveModel = oauth.into();
            oauth_active.token = Set(oauth_token.to_json_value()?);
            oauth_active.update(&self.db).await?;
        }
        
        Ok(())
    }
}