use serde::{Deserialize, Serialize};
use std::str::FromStr;

/// Environment enum for application configuration
#[derive(Debug, Clone)]
pub enum Environment {
    Dev,
    Prod,
    Staging,
}

impl FromStr for Environment {
    type Err = String;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "dev" => Ok(Environment::Dev),
            "staging" => Ok(Environment::Staging),
            "prod" => Ok(Environment::Prod),
            _ => Err(format!("Invalid environment: {}", s)),
        }
    }
}

impl Environment {
    // Convert to string
    pub fn as_str(&self) -> &str {
        match self {
            Environment::Dev => "dev",
            Environment::Prod => "prod",
            Environment::Staging => "staging",
        }
    }

    pub fn as_string(&self) -> String {
        self.as_str().to_string()
    }

    // Check if production
    pub fn is_prod(&self) -> bool {
        matches!(self, Environment::Prod)
    }
}

/// OAuth token structure for Flask-Dance tokens
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OAuthToken {
    pub access_token: String,
    pub refresh_token: String,
}

impl OAuthToken {
    pub fn new(access_token: String, refresh_token: String) -> Self {
        Self {
            access_token,
            refresh_token,
        }
    }
}

/// Helper functions for working with JSON OAuth tokens from Sea-ORM
impl OAuthToken {
    /// Parse from serde_json::Value (what Sea-ORM gives you for JSON columns)
    pub fn from_json_value(value: &serde_json::Value) -> Result<Self, serde_json::Error> {
        serde_json::from_value(value.clone())
    }

    /// Convert to serde_json::Value (for storing in Sea-ORM)
    pub fn to_json_value(&self) -> Result<serde_json::Value, serde_json::Error> {
        serde_json::to_value(self)
    }
}