#[cfg(feature = "ssr")]
use axum::{
    extract::{Query, Extension},
    response::{Redirect, IntoResponse},
    http::StatusCode,
};
#[cfg(feature = "ssr")]
use openidconnect::{
    AuthorizationCode,
    CsrfToken,
    Nonce,
    OAuth2TokenResponse,
    PkceCodeChallenge,
    Scope,
};
#[cfg(feature = "ssr")]
use openidconnect::core::{
    CoreAuthenticationFlow,
};
#[cfg(feature = "ssr")]
use serde::Deserialize;
#[cfg(feature = "ssr")]
use std::sync::Arc;

#[cfg(feature = "ssr")]
use crate::oauth_clients::{OAuthProvider, create_oauth_client, get_oauth_scopes};
#[cfg(feature = "ssr")]
use crate::oauth_state::OAuthState;
#[cfg(feature = "ssr")]
use crate::oauth_profile::fetch_user_profile;
#[cfg(feature = "ssr")]
use crate::auth::{AuthSession, find_or_create_oauth_user};
#[cfg(feature = "ssr")]
use yappr_shared::config::Config;

#[cfg(feature = "ssr")]
#[derive(Deserialize)]
pub struct CallbackParams {
    code: String,
    state: String,
}

#[cfg(feature = "ssr")]
pub async fn handle_oauth_login(
    provider: OAuthProvider,
    Extension(config): Extension<Arc<Config>>,
    Extension(oauth_state): Extension<OAuthState>,
) -> Result<impl IntoResponse, StatusCode> {
    // Get OAuth credentials from config
    let (client_id, client_secret) = match provider {
        OAuthProvider::Discord => (
            config.discord.client_id.clone(),
            config.discord.client_secret.clone(),
        ),
        OAuthProvider::Twitch => (
            config.twitch.client_id.to_string(),
            config.twitch.client_secret.secret().to_string(),
        ),
    };

    // Construct redirect URI (strip trailing slash from server_url)
    let base_url = config.server_url.as_str().trim_end_matches('/');
    let redirect_uri = format!(
        "{}/auth/{}/callback",
        base_url,
        provider.as_str()
    );

    // Create OAuth client
    let client = create_oauth_client(
        provider,
        client_id,
        client_secret,
        redirect_uri,
    ).map_err(|e| {
        tracing::error!("Failed to create OAuth client: {:?}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    // Generate PKCE challenge
    let (pkce_challenge, pkce_verifier) = PkceCodeChallenge::new_random_sha256();

    // Build authorization URL with CSRF token and nonce
    let mut auth_request = client
        .authorize_url(
            CoreAuthenticationFlow::AuthorizationCode,
            CsrfToken::new_random,
            Nonce::new_random,
        )
        .set_pkce_challenge(pkce_challenge);

    // Add scopes
    for scope in get_oauth_scopes(provider) {
        auth_request = auth_request.add_scope(Scope::new(scope));
    }

    let (auth_url, csrf_token, nonce) = auth_request.url();

    // Store the state, nonce, and PKCE verifier
    oauth_state.store_state(
        csrf_token.secret().clone(),
        provider.as_str(),
        nonce,
        pkce_verifier,
    ).await;

    Ok(Redirect::to(auth_url.as_str()))
}


#[cfg(feature = "ssr")]
pub async fn handle_oauth_callback(
    provider: OAuthProvider,
    Query(params): Query<CallbackParams>,
    Extension(config): Extension<Arc<Config>>,
    Extension(oauth_state): Extension<OAuthState>,
    mut auth_session: AuthSession,
) -> Result<impl IntoResponse, StatusCode> {
    // Verify CSRF state and retrieve nonce + PKCE verifier
    let flow_state = oauth_state
        .verify_and_consume(&params.state)
        .await
        .ok_or_else(|| {
            tracing::error!("Invalid or expired OAuth state");
            StatusCode::BAD_REQUEST
        })?;

    if flow_state.provider != provider.as_str() {
        tracing::error!("Provider mismatch in OAuth callback");
        return Err(StatusCode::BAD_REQUEST);
    }

    // Get OAuth credentials from config
    let (client_id, client_secret) = match provider {
        OAuthProvider::Discord => (
            config.discord.client_id.clone(),
            config.discord.client_secret.clone(),
        ),
        OAuthProvider::Twitch => (
            config.twitch.client_id.to_string(),
            config.twitch.client_secret.secret().to_string(),
        ),
    };

    // Construct redirect URI (must match exactly the one used in authorization)
    let base_url = config.server_url.as_str().trim_end_matches('/');
    let redirect_uri = format!(
        "{}/auth/{}/callback",
        base_url,
        provider.as_str()
    );

    // Create OAuth client
    let client = create_oauth_client(
        provider,
        client_id.clone(),
        client_secret.clone(),
        redirect_uri,
    ).map_err(|e| {
        tracing::error!("Failed to create OAuth client: {:?}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    // Exchange authorization code for access token

    // Twitch requires credentials explicitly in the request body
    let mut token_request = client
        .exchange_code(AuthorizationCode::new(params.code))
        .set_pkce_verifier(flow_state.pkce_verifier);

    // Add client_id and client_secret explicitly for Twitch
    if provider == OAuthProvider::Twitch {
        token_request = token_request
            .add_extra_param("client_id", &client_id)
            .add_extra_param("client_secret", &client_secret);
    }

    let token_response = if provider == OAuthProvider::Twitch {
        // Use custom HTTP client for Twitch to fix their non-standard scope array
        use openidconnect::reqwest::async_http_client;
        use openidconnect::HttpResponse;

        token_request
            .request_async(|request| async move {
                // Make the request using the standard client
                async_http_client(request)
                    .await
                    .map(|response| {
                        // Parse the response body as JSON
                        let body = response.body.clone();
                        if let Ok(mut json) = serde_json::from_slice::<serde_json::Value>(&body) {
                            // If scope is an array, convert it to a space-separated string
                            if let Some(scope_array) = json.get("scope").and_then(|s| s.as_array()) {
                                let scope_string = scope_array
                                    .iter()
                                    .filter_map(|v| v.as_str())
                                    .collect::<Vec<_>>()
                                    .join(" ");
                                json["scope"] = serde_json::Value::String(scope_string);

                                // Serialize back to bytes
                                if let Ok(fixed_body) = serde_json::to_vec(&json) {
                                    return HttpResponse {
                                        status_code: response.status_code,
                                        headers: response.headers,
                                        body: fixed_body,
                                    };
                                }
                            }
                        }

                        // If we couldn't parse/fix it, return the original response
                        response
                    })
            })
            .await
            .map_err(|e| {
                tracing::error!("Failed to exchange authorization code: {:?}", e);
                StatusCode::INTERNAL_SERVER_ERROR
            })?
    } else {
        use openidconnect::reqwest::async_http_client;
        token_request
            .request_async(async_http_client)
            .await
            .map_err(|e| {
                tracing::error!("Failed to exchange authorization code: {:?}", e);
                StatusCode::INTERNAL_SERVER_ERROR
            })?
    };

    let access_token = token_response.access_token().secret();
    let refresh_token = token_response.refresh_token().map(|t| t.secret().to_string());
    let expires_in = token_response.expires_in();

    // Note: Discord and Twitch don't provide ID tokens (they're OAuth 2.0, not OIDC)
    // So we need to fetch user profile separately via their APIs

    // Fetch user profile from provider
    let profile = fetch_user_profile(provider, access_token, &client_id)
        .await
        .map_err(|e| {
            tracing::error!("Failed to fetch user profile: {:?}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?;

    // Find or create user in database
    let user = find_or_create_oauth_user(
        auth_session.backend.db.clone(),
        provider,
        &profile,
        access_token,
        refresh_token.as_deref(),
        expires_in,
    )
    .await
    .map_err(|e| {
        tracing::error!("Failed to find or create user: {:?}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    // Log the user in
    auth_session
        .login(&user)
        .await
        .map_err(|e| {
            tracing::error!("Failed to create session: {:?}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?;

    // Redirect to home page
    Ok(Redirect::to("/"))
}
