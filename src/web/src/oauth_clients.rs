#[cfg(feature = "ssr")]
use openidconnect::{
    AuthUrl,
    ClientId,
    ClientSecret,
    EmptyAdditionalProviderMetadata,
    IssuerUrl,
    JsonWebKeySetUrl,
    RedirectUrl,
    ResponseTypes,
    TokenUrl,
};
#[cfg(feature = "ssr")]
use openidconnect::core::{
    CoreClient,
    CoreProviderMetadata,
    CoreResponseType,
    CoreSubjectIdentifierType,
    CoreJwsSigningAlgorithm,
};

#[cfg(feature = "ssr")]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OAuthProvider {
    Discord,
    Twitch,
}

#[cfg(feature = "ssr")]
impl OAuthProvider {
    pub fn as_str(&self) -> &'static str {
        match self {
            OAuthProvider::Discord => "discord",
            OAuthProvider::Twitch => "twitch",
        }
    }

    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "discord" => Some(OAuthProvider::Discord),
            "twitch" => Some(OAuthProvider::Twitch),
            _ => None,
        }
    }
}

#[cfg(feature = "ssr")]
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
        vec![
            ResponseTypes::new(vec![CoreResponseType::Code]),
        ],
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

#[cfg(feature = "ssr")]
pub fn get_oauth_scopes(provider: OAuthProvider) -> Vec<String> {
    match provider {
        OAuthProvider::Discord => vec![
            "identify".to_string(),
            "email".to_string(),
        ],
        OAuthProvider::Twitch => vec![
            "user:read:email".to_string(),
        ],
    }
}
