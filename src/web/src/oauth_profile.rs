#[cfg(feature = "ssr")]
use serde::{Deserialize, Serialize};
#[cfg(feature = "ssr")]
use crate::oauth_clients::OAuthProvider;

#[cfg(feature = "ssr")]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OAuthUserProfile {
    pub provider_user_id: String,
    pub username: String,
    pub email: Option<String>,
    pub avatar_url: Option<String>,
}

#[cfg(feature = "ssr")]
#[derive(Debug, Deserialize)]
struct DiscordUser {
    id: String,
    username: String,
    email: Option<String>,
    avatar: Option<String>,
}

#[cfg(feature = "ssr")]
#[derive(Debug, Deserialize)]
struct TwitchUsersResponse {
    data: Vec<TwitchUser>,
}

#[cfg(feature = "ssr")]
#[derive(Debug, Deserialize)]
struct TwitchUser {
    id: String,
    login: String,
    email: Option<String>,
    profile_image_url: Option<String>,
}

#[cfg(feature = "ssr")]
pub async fn fetch_user_profile(
    provider: OAuthProvider,
    access_token: &str,
    client_id: &str,
) -> Result<OAuthUserProfile, Box<dyn std::error::Error>> {
    match provider {
        OAuthProvider::Discord => fetch_discord_profile(access_token).await,
        OAuthProvider::Twitch => fetch_twitch_profile(access_token, client_id).await,
    }
}

#[cfg(feature = "ssr")]
async fn fetch_discord_profile(
    access_token: &str,
) -> Result<OAuthUserProfile, Box<dyn std::error::Error>> {
    let client = reqwest::Client::new();
    let response = client
        .get("https://discord.com/api/users/@me")
        .header("Authorization", format!("Bearer {}", access_token))
        .send()
        .await?;

    if !response.status().is_success() {
        return Err(format!("Discord API error: {}", response.status()).into());
    }

    let discord_user: DiscordUser = response.json().await?;

    let avatar_url = discord_user.avatar.as_ref().map(|avatar_hash| {
        format!(
            "https://cdn.discordapp.com/avatars/{}/{}.png",
            discord_user.id, avatar_hash
        )
    });

    Ok(OAuthUserProfile {
        provider_user_id: discord_user.id,
        username: discord_user.username,
        email: discord_user.email,
        avatar_url,
    })
}

#[cfg(feature = "ssr")]
async fn fetch_twitch_profile(
    access_token: &str,
    client_id: &str,
) -> Result<OAuthUserProfile, Box<dyn std::error::Error>> {
    let client = reqwest::Client::new();
    let response = client
        .get("https://api.twitch.tv/helix/users")
        .header("Authorization", format!("Bearer {}", access_token))
        .header("Client-Id", client_id)
        .send()
        .await?;

    if !response.status().is_success() {
        return Err(format!("Twitch API error: {}", response.status()).into());
    }

    let twitch_response: TwitchUsersResponse = response.json().await?;
    let twitch_user = twitch_response
        .data
        .into_iter()
        .next()
        .ok_or("No user data returned from Twitch")?;

    Ok(OAuthUserProfile {
        provider_user_id: twitch_user.id,
        username: twitch_user.login,
        email: twitch_user.email,
        avatar_url: twitch_user.profile_image_url,
    })
}
