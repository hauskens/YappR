use eyre::{Context, OptionExt};
use twitch_oauth2::UserToken;
use std::env;
use yappr_shared::database::get_database_connection;
use yappr_shared::services::user::UserService;
use twitch_api::HelixClient;
use twitch_oauth2::{AccessToken, RefreshToken, ClientSecret, ClientId};
use twitch_api::client::ClientDefault;

pub async fn make_token(
    client: &impl twitch_oauth2::client::Client,
    token: impl Into<twitch_oauth2::AccessToken>,
) -> Result<UserToken, eyre::Report> {
    UserToken::from_token(client, token.into())
        .await
        .context("could not get/make access token")}

pub async fn get_user_token() -> Result<UserToken, eyre::Report> {
    let db = get_database_connection().await?;
    let user_service = UserService::new(db);
    let bot_user = user_service.get_bot_user().await?;
    let bot_oauth = user_service.get_user_oauth_token(bot_user.clone().id).await?
        .ok_or_eyre("No OAuth token found for bot user")?;

    
    // Get Twitch app credentials from environment
    let client_id = ClientId::new(env::var("TWITCH_CLIENT_ID").unwrap());
    let client_secret = ClientSecret::new(env::var("TWITCH_CLIENT_SECRET").unwrap());
    let bot_access_token = AccessToken::new(bot_oauth.access_token.clone());
    let bot_refresh_token = RefreshToken::new(bot_oauth.refresh_token.clone());

    
    let client: HelixClient<reqwest::Client> = twitch_api::HelixClient::with_client(
        ClientDefault::default_client_with_name(Some("yappr_bot".parse()?))?
    );
    
    let token = match UserToken::from_existing_or_refresh_token(
        &client,
        bot_access_token.clone(),
        bot_refresh_token.clone(),
        client_id.clone(),
        client_secret.clone(),
    ).await {
        Ok(token) => {
            println!("Successfully created UserToken");
            token
        },
        Err(e) => {
            println!("Failed to create UserToken: {}", e);
            return Err(e.into());
        }
    };
    Ok(token)
}