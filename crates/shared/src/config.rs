use dotenv::dotenv;
use semver::Version;
use std::{env, fmt, net::IpAddr, str::FromStr};
use tracing::{debug, info, instrument, warn};
#[cfg(feature = "twitch")]
use twitch_api;
#[cfg(feature = "twitch")]
use twitch_oauth2;
use url::Url;

/// Configuration field with metadata and value
#[derive(Debug, Clone)]
pub struct ConfigField<T> {
    pub key: &'static str,
    pub description: &'static str,
    pub example: Option<&'static str>,
    pub value: T,
}

// To avoid having to write .value all the time
impl<T> std::ops::Deref for ConfigField<T> {
    type Target = T;

    fn deref(&self) -> &Self::Target {
        &self.value
    }
}

// To avoid having to write .value all the time
impl<T> AsRef<T> for ConfigField<T> {
    fn as_ref(&self) -> &T {
        &self.value
    }
}

#[derive(Debug, Clone)]
pub enum ConfigError {
    MissingEnvVar {
        key: String,
        description: String,
        example: Option<String>,
    },
    InvalidEnvironment {
        key: String,
        value: String,
        description: String,
    },
}

impl fmt::Display for ConfigError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ConfigError::MissingEnvVar {
                key,
                description,
                example,
            } => {
                writeln!(f, "{}:", key)?;
                writeln!(f, "\tDescription: {}", description)?;
                if let Some(ex) = example {
                    writeln!(f, "\tExample: {}={}", key, ex)?;
                }
                Ok(())
            }
            ConfigError::InvalidEnvironment {
                key,
                value,
                description,
            } => {
                writeln!(f, "{}: Invalid value '{}'. {}", key, value, description)
            }
        }
    }
}

#[derive(Debug, Clone)]
pub enum Environment {
    Prod,
    Staging,
    Dev,
}

impl FromStr for Environment {
    type Err = ConfigError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "prod" | "production" => Ok(Self::Prod),
            "stage" | "staging" => Ok(Self::Staging),
            "dev" | "development" => Ok(Self::Dev),
            _ => Err(ConfigError::InvalidEnvironment {
                key: "ENVIRONMENT".to_string(),
                value: s.to_string(),
                description: "Expected 'dev', 'staging', or 'prod'".to_string(),
            }),
        }
    }
}

impl fmt::Display for Environment {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Prod => write!(f, "prod"),
            Self::Staging => write!(f, "staging"),
            Self::Dev => write!(f, "dev"),
        }
    }
}

impl Environment {
    pub fn is_prod(&self) -> bool {
        matches!(self, Self::Prod)
    }
}

#[instrument(level = "debug")]
fn env_parse<T: FromStr>(
    key: &str,
    description: &str,
    example: Option<&str>,
) -> Result<T, ConfigError> {
    match env::var(key) {
        Ok(s) => match s.parse() {
            Ok(parsed) => {
                debug!(key = key, raw_value = %s, "- parsed successfully");
                Ok(parsed)
            }
            Err(_) => {
                warn!(key = key, raw_value = %s, "- failed to parse environment variable");
                Err(ConfigError::InvalidEnvironment {
                    key: key.to_string(),
                    value: s,
                    description: description.to_string(),
                })
            }
        },
        Err(_) => Err(ConfigError::MissingEnvVar {
            key: key.to_string(),
            description: description.to_string(),
            example: example.map(|s| s.to_string()),
        }),
    }
}

#[instrument(level = "debug")]
fn env_required<T: FromStr>(
    key: &'static str,
    description: &'static str,
    example: Option<&'static str>,
) -> Result<ConfigField<T>, ConfigError> {
    match env_parse(key, description, example) {
        Ok(value) => Ok(ConfigField {
            key,
            description,
            example,
            value,
        }),
        Err(e) => Err(e),
    }
}

// Helper for parsed types - accepts any value that can be displayed as string
#[instrument(level = "debug", skip(default))]
fn env_or_default<T: FromStr>(
    key: &'static str,
    description: &'static str,
    example: Option<&'static str>,
    default: impl fmt::Display,
) -> ConfigField<T>
where
    <T as FromStr>::Err: std::fmt::Debug,
{
    let value = match env_parse(key, description, example) {
        Ok(value) => value,
        Err(_) => {
            let default_str = default.to_string();
            default_str.parse().unwrap_or_else(|e| {
                panic!(
                    "Failed to parse default value '{}' for {}: {:?}",
                    default_str, key, e
                )
            })
        }
    };
    ConfigField {
        key,
        description,
        example,
        value,
    }
}

#[instrument(level = "debug")]
fn env_or_option<T: FromStr>(
    key: &'static str,
    description: &'static str,
    example: Option<&'static str>,
) -> ConfigField<Option<T>> {
    let value = env_parse(key, description, example).ok();
    ConfigField {
        key,
        description,
        example,
        value,
    }
}

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
}

impl Config {
    #[instrument(level = "info")]
    pub fn load() -> Self {
        info!("Loading application configuration");
        let _ = dotenv();

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
                Some("false"),
                false,
            ),
            server_port: env_or_default(
                "PORT",
                "Port number for the HTTP server to listen on",
                Some("5000"),
                5000,
            ),
            server_host: env_or_default(
                "HOST",
                "IP address for the server to bind to (0.0.0.0 for all interfaces)",
                Some("0.0.0.0"),
                "0.0.0.0",
            ),
            server_url: env_or_default(
                "SERVER_URL",
                "Public URL where this service is accessible (used for OAuth redirects)",
                Some("https://yappr.example.com"),
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
                Some("http://loki:3100"),
            ),
            storage_location: env_or_default(
                "STORAGE_LOCATION",
                "File system path for storing application data",
                Some("/var/lib/yappr/data"),
                "/var/lib/yappr/data",
            ),
            session_secret: env_or_default(
                "SESSION_SECRET",
                "Secret key for session encryption (minimum 32 characters). CHANGE IN PRODUCTION!",
                Some("your-secret-key-min-32-chars-long"),
                "dev-secret-change-in-production-min-32-chars",
            ),
            version: ConfigField {
                key: "CARGO_PKG_VERSION",
                description: "Package version from Cargo.toml (auto-populated at compile time)",
                example: Some("1.0.0"),
                value: Version::parse(env!("CARGO_PKG_VERSION")).unwrap(),
            },
            #[cfg(feature = "twitch")]
            bot_user_id: {
                let field = env_or_option::<String>(
                    "BOT_USER_ID",
                    "Twitch user ID for the bot account (optional)",
                    Some("123456789"),
                );
                ConfigField {
                    key: field.key,
                    description: field.description,
                    example: field.example,
                    value: field.value.map(twitch_api::types::UserId::from),
                }
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
            Some("postgresql://user:password@localhost:5432/yappr"),
        );
        if let Err(e) = &url {
            errors.push(e.clone());
        }

        DatabaseConfig {
            url: url.unwrap(),
            max_connections: env_or_default(
                "DB_MAX_CONNECTIONS",
                "Maximum number of database connections in the pool",
                Some("100"),
                100,
            ),
            min_connections: env_or_default(
                "DB_MIN_CONNECTIONS",
                "Minimum number of database connections to maintain",
                Some("5"),
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
            Some("abc123xyz..."),
        );
        if let Err(e) = &client_id {
            errors.push(e.clone());
        }

        let client_secret = env_required(
            "TWITCH_CLIENT_SECRET",
            "OAuth client secret from Twitch Developer Console",
            Some("your-client-secret"),
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
            Some("AIza..."),
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
            Some("123456789012345678"),
        );
        if let Err(e) = &client_id {
            errors.push(e.clone());
        }

        let client_secret = env_required(
            "DISCORD_CLIENT_SECRET",
            "OAuth client secret from Discord Developer Portal",
            Some("your-client-secret"),
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
                Some("Bot MTk4NjIyNDgzN..."),
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
                Some("nats://localhost:4222"),
                "nats://localhost:4222",
            ),
        }
    }
}
