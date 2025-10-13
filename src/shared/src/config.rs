use dotenv::dotenv;
use std::{env, str::FromStr, net::IpAddr};
use crate::models::shared::Environment;
use semver::Version;
use url::Url;
use tracing::{info, warn, error, instrument, debug};
#[cfg(feature = "twitch")]
use twitch_oauth2;


// Helper for strings
#[instrument(level = "debug")]
fn env_or(key: &str, default: &str) -> String {
    let value = env::var(key).unwrap_or_else(|_| {
        debug!(key = key, default_value = default, "Using default environment value");
        default.to_string()
    });
    debug!(key = key, value = %value, "Environment variable loaded");
    value
}

#[instrument(level = "debug")]
fn env_or_option(key: &str) -> Option<String> {
    let value = env::var(key).ok();
    match &value {
        Some(v) => debug!(key = key, value = %v, "Optional environment variable found"),
        None => debug!(key = key, "Optional environment variable not set"),
    }
    value
}

// Helper for parsed types
#[instrument(level = "debug", skip(default))]
fn env_or_parse<T: FromStr>(key: &str, default: T) -> T {
    match env::var(key) {
        Ok(s) => match s.parse() {
            Ok(parsed) => {
                debug!(key = key, raw_value = %s, "Environment variable parsed successfully");
                parsed
            }
            Err(_) => {
                warn!(key = key, raw_value = %s, "Failed to parse environment variable, using default");
                default
            }
        }
        Err(_) => {
            debug!(key = key, "Environment variable not set, using default");
            default
        }
    }
}

#[instrument(level = "debug")]
fn env_required(key: &str) -> String {
    match env::var(key) {
        Ok(value) => {
            debug!(key = key, "Required environment variable loaded");
            value
        }
        Err(_) => {
            error!(key = key, "Required environment variable not set");
            panic!("Environment variable '{}' is required but was not set", key)
        }
    }
}

#[derive(Debug, Clone)]
pub struct Config {
    // Application settings
    pub debug: bool,
    pub server_port: u16,
    pub server_host: IpAddr,
    pub environment: Environment,
    pub service_name: String,
    pub version: Version,
    pub loki_url: Option<Url>,
    

    #[cfg(feature = "database")]
    pub database: DatabaseConfig,

    #[cfg(feature = "twitch")]
    pub twitch: TwitchConfig,

    #[cfg(feature = "youtube")]
    pub youtube: YouTubeConfig,

    #[cfg(feature = "discord")]
    pub discord: DiscordConfig,


}

#[derive(Debug, Clone)]
pub struct TwitchConfig {
    pub client_id: twitch_oauth2::ClientId,
    pub client_secret: twitch_oauth2::ClientSecret,
}

#[derive(Debug, Clone)]
pub struct YouTubeConfig {
    pub api_key: String,
}

#[derive(Debug, Clone)]
pub struct DiscordConfig {
    pub client_id: String,
    pub client_secret: String,
}

#[derive(Debug, Clone)]
pub struct DatabaseConfig {
    pub url: String,
    pub max_connections: u32,
    pub min_connections: u32,
}

impl Config {
    #[instrument(level = "info")]
    pub fn load() -> Self {
        info!("Loading application configuration");
        let _ = dotenv();

        let config = Config {
            debug: env_or_parse("DEBUG", false),
            server_port: env_or_parse("PORT", 5000),
            server_host: env_or("HOST", "0.0.0.0").parse::<IpAddr>().expect("Invalid ip address format"),
            environment: env_or("ENVIRONMENT", "dev").parse::<Environment>().expect("Invalid environment name"),
            service_name: env_required("SERVICE_NAME"),
            version: env_or("VERSION", "0.0.0").replace(":", "").parse::<Version>().expect("Invalid version format"),
            loki_url: env_or_option("LOKI_URL").map(|url| Url::parse(&url).expect("Invalid loki url format")),
            #[cfg(feature = "database")]
            database: DatabaseConfig::load(),
            #[cfg(feature = "twitch")]
            twitch: TwitchConfig::load(),
            #[cfg(feature = "youtube")]
            youtube: YouTubeConfig::load(),
            #[cfg(feature = "discord")]
            discord: DiscordConfig::load(),
        };

        info!(
            service_name = %config.service_name,
            version = %config.version,
            environment = %config.environment.as_string(),
            debug = config.debug,
            "Configuration loaded successfully"
        );

        config
    }


}

impl DatabaseConfig {
    #[instrument(level = "debug")]
    pub fn load() -> Self {
        debug!("Loading database configuration");
        let config = DatabaseConfig {
            url: env_or("DB_URI", "postgresql://postgres:mysecretpassword@localhost:5432/postgres").replace("+psycopg", ""),
            max_connections: env_or_parse("DB_MAX_CONNECTIONS", 100),
            min_connections: env_or_parse("DB_MIN_CONNECTIONS", 5),
        };
        debug!(
            max_connections = config.max_connections,
            min_connections = config.min_connections,
            "Database configuration loaded"
        );
        config
    }
}

impl TwitchConfig {
    #[instrument(level = "debug")]
    pub fn load() -> Self {
        debug!("Loading Twitch API configuration");
        let config = TwitchConfig {
            client_id: env_required("TWITCH_CLIENT_ID").parse::<twitch_oauth2::ClientId>().expect("Invalid client id"),
            client_secret: env_required("TWITCH_CLIENT_SECRET").parse::<twitch_oauth2::ClientSecret>().expect("Invalid client secret"),
        };
        debug!("Twitch API configuration loaded successfully");
        config
    }
}

impl YouTubeConfig {
    #[instrument(level = "debug")]
    pub fn load() -> Self {
        debug!("Loading YouTube API configuration");
        let config = YouTubeConfig {
            api_key: env_required("YOUTUBE_API_KEY"),
        };
        debug!("YouTube API configuration loaded successfully");
        config
    }
}

impl DiscordConfig {
    #[instrument(level = "debug")]
    pub fn load() -> Self {
        debug!("Loading Discord API configuration");
        let config = DiscordConfig {
            client_id: env_required("DISCORD_CLIENT_ID"),
            client_secret: env_required("DISCORD_CLIENT_SECRET"),
        };
        debug!("Discord API configuration loaded successfully");
        config
    }
}
