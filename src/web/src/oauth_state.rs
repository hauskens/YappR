#[cfg(feature = "ssr")]
use std::collections::HashMap;
#[cfg(feature = "ssr")]
use std::sync::Arc;
#[cfg(feature = "ssr")]
use tokio::sync::RwLock;
#[cfg(feature = "ssr")]
use openidconnect::{Nonce, PkceCodeVerifier};

#[cfg(feature = "ssr")]
#[derive(Clone)]
pub struct OAuthState {
    // In-memory storage for OAuth flow state
    // Format: state_token -> (provider, nonce, pkce_verifier, timestamp)
    states: Arc<RwLock<HashMap<String, (String, Nonce, PkceCodeVerifier, std::time::Instant)>>>,
}

#[cfg(feature = "ssr")]
pub struct OAuthFlowState {
    pub provider: String,
    pub nonce: Nonce,
    pub pkce_verifier: PkceCodeVerifier,
}

#[cfg(feature = "ssr")]
impl OAuthState {
    pub fn new() -> Self {
        Self {
            states: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    /// Store OAuth flow state (CSRF token, nonce, PKCE verifier)
    pub async fn store_state(
        &self,
        state: String,
        provider: &str,
        nonce: Nonce,
        pkce_verifier: PkceCodeVerifier,
    ) {
        let mut states = self.states.write().await;
        states.insert(
            state,
            (provider.to_string(), nonce, pkce_verifier, std::time::Instant::now())
        );

        // Clean up old states (older than 10 minutes)
        let now = std::time::Instant::now();
        states.retain(|_, (_, _, _, timestamp)| {
            now.duration_since(*timestamp).as_secs() < 600
        });
    }

    /// Verify and consume a state token, returning all stored OAuth flow data
    pub async fn verify_and_consume(&self, state: &str) -> Option<OAuthFlowState> {
        let mut states = self.states.write().await;

        if let Some((provider, nonce, pkce_verifier, timestamp)) = states.remove(state) {
            // Check if state is not expired (10 minutes)
            let now = std::time::Instant::now();
            if now.duration_since(timestamp).as_secs() < 600 {
                return Some(OAuthFlowState {
                    provider,
                    nonce,
                    pkce_verifier,
                });
            }
        }

        None
    }
}

#[cfg(feature = "ssr")]
impl Default for OAuthState {
    fn default() -> Self {
        Self::new()
    }
}
