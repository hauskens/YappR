use config_loadr::{ConfigError, ConfigField, env_or_default, env_or_option, env_required};
use semver::Version;
use std::{env, net::IpAddr};
use tracing::{debug, info, instrument, warn};
#[cfg(feature = "twitch")]
use twitch_api;
#[cfg(feature = "twitch")]
use twitch_oauth2;
use url::Url;

// Re-export for backwards compatibility with rest of the codebase
pub use config_loadr::Environment;

/// Main application configuration
#[derive(Debug, Clone)]
pub struct Config {
    // Application settings
    pub debug: ConfigField<bool>,
    pub server_port: ConfigField<u16>,
    pub server_host: ConfigField<IpAddr>,
    pub server_url: ConfigField<Url>,
    pub environment: ConfigField<Environment>,
    pub service_name: ConfigField<String>,
    pub version: ConfigField<Version>,
    pub loki_url: ConfigField<Option<Url>>,
    pub storage_location: ConfigField<String>,
    pub session_secret: ConfigField<String>,
    #[cfg(feature = "twitch")]
    pub bot_user_id: ConfigField<Option<twitch_api::types::UserId>>,

    #[cfg(feature = "database")]
    pub database: DatabaseConfig,

    #[cfg(feature = "twitch")]
    pub twitch: TwitchConfig,

    #[cfg(feature = "youtube")]
    pub youtube: YouTubeConfig,

    #[cfg(feature = "discord")]
    pub discord: DiscordConfig,

    #[cfg(feature = "job-queue")]
    pub nats: NATSConfig,
}

#[cfg(feature = "twitch")]
#[derive(Debug, Clone)]
pub struct TwitchConfig {
    pub client_id: ConfigField<twitch_oauth2::ClientId>,
    pub client_secret: ConfigField<twitch_oauth2::ClientSecret>,
}

#[cfg(feature = "youtube")]
#[derive(Debug, Clone)]
pub struct YouTubeConfig {
    pub api_key: ConfigField<String>,
}

#[cfg(feature = "discord")]
#[derive(Debug, Clone)]
pub struct DiscordConfig {
    pub client_id: ConfigField<String>,
    pub client_secret: ConfigField<String>,
    pub bot_token: ConfigField<Option<String>>,
}

#[cfg(feature = "database")]
#[derive(Debug, Clone)]
pub struct DatabaseConfig {
    pub url: ConfigField<String>,
    pub max_connections: ConfigField<u32>,
    pub min_connections: ConfigField<u32>,
}

#[cfg(feature = "job-queue")]
#[derive(Debug, Clone)]
pub struct NATSConfig {
    pub url: ConfigField<String>,
    pub worker_queues: ConfigField<String>,
}

impl Config {
    #[instrument(level = "info")]
    pub fn load() -> Self {
        info!("Loading application configuration");
        config_loadr::load_dotenv();

        let mut errors = Vec::new();

        // Load all required values
        let service_name = env_required(
            "SERVICE_NAME",
            "The name of this service instance (e.g., 'yappr-web', 'yappr-worker')",
            Some("yappr-web"),
        );
        if let Err(e) = &service_name {
            errors.push(e.clone());
        }

        let environment = env_required(
            "ENVIRONMENT",
            "Runtime environment, i.e. 'dev', 'staging', or 'prod'",
            Some("prod"),
        );
        if let Err(e) = &environment {
            errors.push(e.clone());
        }

        // Load sub-configs
        #[cfg(feature = "database")]
        let database = DatabaseConfig::load(&mut errors);

        #[cfg(feature = "twitch")]
        let twitch = TwitchConfig::load(&mut errors);

        #[cfg(feature = "youtube")]
        let youtube = YouTubeConfig::load(&mut errors);

        #[cfg(feature = "discord")]
        let discord = DiscordConfig::load(&mut errors);

        #[cfg(feature = "job-queue")]
        let nats = NATSConfig::load(&mut errors);

        // If errors, panic with a summary
        if !errors.is_empty() {
            let error_summary = errors
                .iter()
                .map(|e| format!("  - {}", e))
                .collect::<Vec<_>>()
                .join("\n");
            panic!(
                "Configuration failed with {} error(s):\n{}",
                errors.len(),
                error_summary
            );
        }

        Config {
            debug: env_or_default(
                "DEBUG",
                "Enable debug mode (true/false). Provides verbose logging and error messages.",
                "false",
                false,
            ),
            server_port: env_or_default(
                "PORT",
                "Port number for the HTTP server to listen on",
                "5000",
                5000,
            ),
            server_host: env_or_default(
                "HOST",
                "IP address for the server to bind to (0.0.0.0 for all interfaces)",
                "0.0.0.0",
                "0.0.0.0",
            ),
            server_url: env_or_default(
                "SERVER_URL",
                "Public URL where this service is accessible (used for OAuth redirects)",
                "https://yappr.example.com",
                "http://localhost:3000",
            ),
            environment: environment.unwrap(),
            // environment: env_or_default(
            //     "ENVIRONMENT",
            //     "Runtime environment: 'dev', 'staging', or 'prod'",
            //     Some("prod"),
            //     "dev",
            // ),
            service_name: service_name.unwrap(),
            loki_url: env_or_option(
                "LOKI_URL",
                "Loki server URL for centralized logging (optional)",
                "http://loki:3100",
            ),
            storage_location: env_or_default(
                "STORAGE_LOCATION",
                "File system path for storing application data",
                "/var/lib/yappr/data",
                "/var/lib/yappr/data",
            ),
            session_secret: env_or_default(
                "SESSION_SECRET",
                "Secret key for session encryption (minimum 32 characters). CHANGE IN PRODUCTION!",
                "your-secret-key-min-32-chars-long",
                "dev-secret-change-in-production-min-32-chars",
            ),
            version: ConfigField::required(
                "CARGO_PKG_VERSION",
                "Package version from Cargo.toml (auto-populated at compile time)",
                "1.0.0",
                Version::parse(env!("CARGO_PKG_VERSION")).unwrap(),
            ),
            #[cfg(feature = "twitch")]
            bot_user_id: {
                env_or_option::<twitch_api::types::UserId>(
                    "BOT_USER_ID",
                    "Twitch user ID for the bot account (optional)",
                    "123456789",
                )
            },
            #[cfg(feature = "database")]
            database,
            #[cfg(feature = "twitch")]
            twitch,
            #[cfg(feature = "youtube")]
            youtube,
            #[cfg(feature = "discord")]
            discord,
            #[cfg(feature = "job-queue")]
            nats,
        }
    }
}

#[cfg(feature = "database")]
impl DatabaseConfig {
    #[instrument(level = "debug")]
    pub fn load(errors: &mut Vec<ConfigError>) -> Self {
        let url = env_required(
            "DB_URI",
            "PostgreSQL connection string",
            "postgresql://user:password@localhost:5432/yappr",
        );
        if let Err(e) = &url {
            errors.push(e.clone());
        }

        DatabaseConfig {
            url: url.unwrap(),
            max_connections: env_or_default(
                "DB_MAX_CONNECTIONS",
                "Maximum number of database connections in the pool",
                "100",
                100,
            ),
            min_connections: env_or_default(
                "DB_MIN_CONNECTIONS",
                "Minimum number of database connections to maintain",
                "5",
                5,
            ),
        }
    }
}

#[cfg(feature = "twitch")]
impl TwitchConfig {
    #[instrument(level = "debug")]
    pub fn load(errors: &mut Vec<ConfigError>) -> Self {
        let client_id = env_required(
            "TWITCH_CLIENT_ID",
            "OAuth client ID from Twitch Developer Console (https://dev.twitch.tv/console)",
            "abc123xyz...",
        );
        if let Err(e) = &client_id {
            errors.push(e.clone());
        }

        let client_secret = env_required(
            "TWITCH_CLIENT_SECRET",
            "OAuth client secret from Twitch Developer Console",
            "your-client-secret",
        );
        if let Err(e) = &client_secret {
            errors.push(e.clone());
        }

        TwitchConfig {
            client_id: client_id.unwrap(),
            client_secret: client_secret.unwrap(),
        }
    }
}

#[cfg(feature = "youtube")]
impl YouTubeConfig {
    #[instrument(level = "debug")]
    pub fn load(errors: &mut Vec<ConfigError>) -> Self {
        let api_key = env_required(
            "YOUTUBE_API_KEY",
            "API key from Google Cloud Console with YouTube Data API v3 enabled",
            "AIza...",
        );
        if let Err(e) = &api_key {
            errors.push(e.clone());
        }

        YouTubeConfig {
            api_key: api_key.unwrap(),
        }
    }
}

#[cfg(feature = "discord")]
impl DiscordConfig {
    #[instrument(level = "debug")]
    pub fn load(errors: &mut Vec<ConfigError>) -> Self {
        let client_id = env_required(
            "DISCORD_CLIENT_ID",
            "OAuth client ID from Discord Developer Portal (https://discord.com/developers)",
            "123456789012345678",
        );
        if let Err(e) = &client_id {
            errors.push(e.clone());
        }

        let client_secret = env_required(
            "DISCORD_CLIENT_SECRET",
            "OAuth client secret from Discord Developer Portal",
            "your-client-secret",
        );
        if let Err(e) = &client_secret {
            errors.push(e.clone());
        }

        DiscordConfig {
            client_id: client_id.unwrap(),
            client_secret: client_secret.unwrap(),
            bot_token: env_or_option(
                "DISCORD_BOT_TOKEN",
                "Bot token from Discord Developer Portal (optional, for bot features)",
                "Bot MTk4NjIyNDgzN...",
            ),
        }
    }
}

#[cfg(feature = "job-queue")]
impl NATSConfig {
    #[instrument(level = "debug")]
    pub fn load(errors: &mut Vec<ConfigError>) -> Self {
        NATSConfig {
            url: env_or_default(
                "NATS_URL",
                "NATS server connection URL for job queue",
                "nats://localhost:4222",
                "nats://localhost:4222",
            ),
            worker_queues: env_or_default(
                "WORKER_QUEUES",
                "Comma-separated list of job queues this worker should handle",
                "general",
                "general",
            ),
        }
    }
}

/// Configuration for a single scheduled job
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct JobConfig {
    pub enabled: bool,
    pub schedule: String,
}

impl Default for JobConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            schedule: "0 0 * * * *".to_string(), // Every hour by default
        }
    }
}

/// Configuration for all scheduled jobs in the orchestrator
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct JobsConfig {
    #[serde(default = "default_fetch_videos_config")]
    pub fetch_videos: JobConfig,
    #[serde(default = "default_update_videos_config")]
    pub update_videos: JobConfig,
}

fn default_fetch_videos_config() -> JobConfig {
    JobConfig {
        enabled: true,
        schedule: "0 */15 * * * *".to_string(), // Every 15 minutes
    }
}

fn default_update_videos_config() -> JobConfig {
    JobConfig {
        enabled: true,
        schedule: "0 0 */6 * * *".to_string(), // Every 6 hours
    }
}

impl Default for JobsConfig {
    fn default() -> Self {
        Self {
            fetch_videos: default_fetch_videos_config(),
            update_videos: default_update_videos_config(),
        }
    }
}

impl JobsConfig {
    /// Load jobs configuration from environment variable
    /// Expects JSON format in JOBS_CONFIG env var
    #[instrument(level = "info")]
    pub fn load() -> Self {
        info!("Loading jobs configuration");

        match env::var("JOBS_CONFIG") {
            Ok(json_str) => {
                debug!(config_json = %json_str, "Parsing JOBS_CONFIG");
                match serde_json::from_str::<JobsConfig>(&json_str) {
                    Ok(config) => {
                        info!("Jobs configuration loaded from JOBS_CONFIG");
                        config
                    }
                    Err(e) => {
                        warn!(
                            error = %e,
                            "Failed to parse JOBS_CONFIG, using defaults"
                        );
                        Self::default()
                    }
                }
            }
            Err(_) => {
                info!("JOBS_CONFIG not set, using default configuration");
                Self::default()
            }
        }
    }
}
