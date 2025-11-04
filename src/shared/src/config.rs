use crate::types::Environment;
use dotenv::dotenv;
use semver::Version;
use std::{env, net::IpAddr, str::FromStr};
use tracing::{debug, error, info, instrument, warn};
#[cfg(feature = "twitch")]
use twitch_api;
#[cfg(feature = "twitch")]
use twitch_oauth2;
use url::Url;

// Helper for strings
#[instrument(level = "debug")]
fn env_or(key: &str, default: &str) -> String {
    let value = env::var(key).unwrap_or_else(|_| {
        debug!(
            key = key,
            default_value = default,
            "Using default environment value"
        );
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
        },
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
    pub server_url: Url,
    pub environment: Environment,
    pub service_name: String,
    pub version: Version,
    pub loki_url: Option<Url>,
    pub storage_location: String,
    pub session_secret: String,
    #[cfg(feature = "twitch")]
    pub bot_user_id: Option<twitch_api::types::UserId>,

    #[cfg(feature = "database")]
    pub database: DatabaseConfig,

    #[cfg(feature = "twitch")]
    pub twitch: TwitchConfig,

    #[cfg(feature = "youtube")]
    pub youtube: YouTubeConfig,

    #[cfg(feature = "discord")]
    pub discord: DiscordConfig,

    #[cfg(feature = "redis-client")]
    pub redis: RedisConfig,

    #[cfg(feature = "job-queue")]
    pub nats: NATSConfig,
}

#[cfg(feature = "twitch")]
#[derive(Debug, Clone)]
pub struct TwitchConfig {
    pub client_id: twitch_oauth2::ClientId,
    pub client_secret: twitch_oauth2::ClientSecret,
}

#[cfg(feature = "youtube")]
#[derive(Debug, Clone)]
pub struct YouTubeConfig {
    pub api_key: String,
}

#[cfg(feature = "discord")]
#[derive(Debug, Clone)]
pub struct DiscordConfig {
    pub client_id: String,
    pub client_secret: String,
}

#[cfg(feature = "database")]
#[derive(Debug, Clone)]
pub struct DatabaseConfig {
    pub url: String,
    pub max_connections: u32,
    pub min_connections: u32,
}

#[cfg(feature = "redis-client")]
#[derive(Debug, Clone)]
pub enum RedisScheme {
    Redis,       // redis://
    RedisTls,    // rediss://
    RedisSocket, // redis+unix://
}

#[cfg(feature = "job-queue")]
#[derive(Debug, Clone)]
pub struct NATSConfig {
    pub url: String,
}

#[cfg(feature = "redis-client")]
impl FromStr for RedisScheme {
    type Err = String;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s.to_lowercase().as_str() {
            "redis" => Ok(RedisScheme::Redis),
            "rediss" => Ok(RedisScheme::RedisTls),
            "redis+unix" => Ok(RedisScheme::RedisSocket),
            _ => Err(format!(
                "Invalid Redis scheme: '{}'. Valid options are: redis, rediss, redis+unix",
                s
            )),
        }
    }
}

#[cfg(feature = "redis-client")]
#[derive(Debug, Clone)]
pub struct RedisConfig {
    pub scheme: RedisScheme,
    pub host: String,
    pub port: u16,
}

impl Config {
    #[instrument(level = "info")]
    pub fn load() -> Self {
        info!("Loading application configuration");
        let _ = dotenv();

        let config = Config {
            debug: env_or_parse("DEBUG", false),
            server_port: env_or_parse("PORT", 5000),
            server_host: env_or("HOST", "0.0.0.0")
                .parse::<IpAddr>()
                .expect("Invalid ip address format"),
            server_url: env_or("SERVER_URL", "http://localhost:3000")
                .parse::<Url>()
                .expect("Invalid server url format"),
            environment: env_or("ENVIRONMENT", "dev")
                .parse::<Environment>()
                .expect("Invalid environment name"),
            service_name: env_required("SERVICE_NAME"),
            version: env_or("VERSION", "0.0.0")
                .replace(":", "")
                .parse::<Version>()
                .expect("Invalid version format"),
            loki_url: env_or_option("LOKI_URL")
                .map(|url| Url::parse(&url).expect("Invalid loki url format")),
            storage_location: env_or("STORAGE_LOCATION", "/var/lib/yappr/data"),
            session_secret: env_or(
                "SESSION_SECRET",
                "dev-secret-change-in-production-min-32-chars",
            ),
            #[cfg(feature = "twitch")]
            bot_user_id: env_or_option("BOT_USER_ID").map(twitch_api::types::UserId::from),
            #[cfg(feature = "database")]
            database: DatabaseConfig::load(),
            #[cfg(feature = "twitch")]
            twitch: TwitchConfig::load(),
            #[cfg(feature = "youtube")]
            youtube: YouTubeConfig::load(),
            #[cfg(feature = "discord")]
            discord: DiscordConfig::load(),
            #[cfg(feature = "redis-client")]
            redis: RedisConfig::load(),
            #[cfg(feature = "job-queue")]
            nats: NATSConfig::load(),
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

#[cfg(feature = "database")]
impl DatabaseConfig {
    #[instrument(level = "debug")]
    pub fn load() -> Self {
        debug!("Loading database configuration");
        let config = DatabaseConfig {
            url: env_or(
                "DB_URI",
                "postgresql://postgres:mysecretpassword@localhost:5432/postgres",
            )
            .replace("+psycopg", ""),
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

#[cfg(feature = "redis-client")]
impl RedisConfig {
    #[instrument(level = "debug")]
    pub fn connection_string(&self) -> String {
        let scheme = match self.scheme {
            RedisScheme::Redis => "redis",
            RedisScheme::RedisTls => "rediss",
            RedisScheme::RedisSocket => "redis+unix",
        };
        format!("{}://{}:{}", scheme, self.host, self.port)
    }
    #[instrument(level = "debug")]
    pub fn load() -> Self {
        debug!("Loading Redis configuration");
        let config = RedisConfig {
            scheme: env_or("REDIS_SCHEME", "redis")
                .parse::<RedisScheme>()
                .expect("Invalid Redis scheme"),
            host: env_or("REDIS_HOST", "localhost"),
            port: env_or_parse("REDIS_PORT", 6379),
        };
        debug!(
            "Redis configuration loaded: {:?}://{}:{}",
            config.scheme, config.host, config.port
        );
        config
    }
}

#[cfg(feature = "twitch")]
impl TwitchConfig {
    #[instrument(level = "debug")]
    pub fn load() -> Self {
        debug!("Loading Twitch API configuration");
        let config = TwitchConfig {
            client_id: env_required("TWITCH_CLIENT_ID")
                .parse::<twitch_oauth2::ClientId>()
                .expect("Invalid client id"),
            client_secret: env_required("TWITCH_CLIENT_SECRET")
                .parse::<twitch_oauth2::ClientSecret>()
                .expect("Invalid client secret"),
        };
        debug!("Twitch API configuration loaded successfully");
        config
    }
}

#[cfg(feature = "youtube")]
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

#[cfg(feature = "discord")]
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

#[cfg(feature = "job-queue")]
impl NATSConfig {
    #[instrument(level = "debug")]
    pub fn load() -> Self {
        debug!("Loading NATS configuration");
        let config = NATSConfig {
            url: env_or("NATS_URL", "nats://localhost:4222"),
        };
        debug!("NATS configuration loaded: {}", config.url);
        config
    }
}
