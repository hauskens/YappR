use openidconnect::core::{
    CoreClient, CoreJwsSigningAlgorithm, CoreProviderMetadata, CoreResponseType,
    CoreSubjectIdentifierType,
};
use openidconnect::{
    AuthUrl, ClientId, ClientSecret, EmptyAdditionalProviderMetadata, IssuerUrl, JsonWebKeySetUrl,
    RedirectUrl, ResponseTypes, TokenUrl,
};
use std::str::FromStr;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OAuthProvider {
    Discord,
    Twitch,
}

impl OAuthProvider {
    pub fn as_str(&self) -> &'static str {
        match self {
            OAuthProvider::Discord => "discord",
            OAuthProvider::Twitch => "twitch",
        }
    }
}

impl FromStr for OAuthProvider {
    type Err = &'static str;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "discord" => Ok(OAuthProvider::Discord),
            "twitch" => Ok(OAuthProvider::Twitch),
            _ => Err("Invalid OAuth provider"),
        }
    }
}

pub fn create_oauth_client(
    provider: OAuthProvider,
    client_id: String,
    client_secret: String,
    redirect_uri: String,
) -> Result<CoreClient, Box<dyn std::error::Error>> {
    let (issuer_url, auth_url, token_url, jwks_url) = match provider {
        OAuthProvider::Discord => (
            "https://discord.com",
            "https://discord.com/api/oauth2/authorize",
            "https://discord.com/api/oauth2/token",
            "https://discord.com/.well-known/jwks.json",
        ),
        OAuthProvider::Twitch => (
            "https://id.twitch.tv",
            "https://id.twitch.tv/oauth2/authorize",
            "https://id.twitch.tv/oauth2/token",
            "https://id.twitch.tv/oauth2/keys",
        ),
    };

    // Manually construct provider metadata since Discord/Twitch don't support OIDC discovery
    // They are OAuth 2.0 providers, not full OpenID Connect providers
    let provider_metadata = CoreProviderMetadata::new(
        IssuerUrl::new(issuer_url.to_string())?,
        AuthUrl::new(auth_url.to_string())?,
        JsonWebKeySetUrl::new(jwks_url.to_string())?,
        vec![ResponseTypes::new(vec![CoreResponseType::Code])],
        vec![CoreSubjectIdentifierType::Public],
        vec![CoreJwsSigningAlgorithm::RsaSsaPkcs1V15Sha256],
        EmptyAdditionalProviderMetadata {},
    )
    .set_token_endpoint(Some(TokenUrl::new(token_url.to_string())?));

    let client = CoreClient::from_provider_metadata(
        provider_metadata,
        ClientId::new(client_id),
        Some(ClientSecret::new(client_secret)),
    )
    .set_redirect_uri(RedirectUrl::new(redirect_uri)?);

    Ok(client)
}

pub fn get_oauth_scopes(provider: OAuthProvider) -> Vec<String> {
    match provider {
        OAuthProvider::Discord => vec!["identify".to_string(), "email".to_string()],
        OAuthProvider::Twitch => vec!["user:read:email".to_string()],
    }
}
