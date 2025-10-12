use dotenv::dotenv;
use std::{env, str::FromStr, net::IpAddr};
use crate::models::shared::Environment;
use semver::Version;
#[cfg(feature = "twitch")]
use twitch_oauth2;


// Helper for strings
fn env_or(key: &str, default: &str) -> String {
    env::var(key).unwrap_or_else(|_| default.to_string())
}

// Helper for parsed types
fn env_or_parse<T: FromStr>(key: &str, default: T) -> T {
    env::var(key)
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(default)
}

fn env_required(key: &str) -> String {
    env::var(key).unwrap_or_else(|_| {
        panic!("Environment variable '{}' is required but was not set", key)
    })
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
    pub fn load() -> Self {
        let _ = dotenv();

        Config {
            debug: env_or_parse("DEBUG", false),
            server_port: env_or_parse("PORT", 5000),
            server_host: env_or("HOST", "0.0.0.0").parse::<IpAddr>().expect("Invalid ip address format"),
            environment: env_or("ENVIRONMENT", "dev").parse::<Environment>().expect("Invalid environment name"),
            service_name: env_required("SERVICE_NAME"),
            version: env_or("VERSION", "0.0.0").replace(":", "").parse::<Version>().expect("Invalid version format"),
            #[cfg(feature = "database")]
            database: DatabaseConfig::load(),
            #[cfg(feature = "twitch")]
            twitch: TwitchConfig::load(),
            #[cfg(feature = "youtube")]
            youtube: YouTubeConfig::load(),
            #[cfg(feature = "discord")]
            discord: DiscordConfig::load(),
        }
    }


}

impl DatabaseConfig {
    pub fn load() -> Self {
        DatabaseConfig {
            url: env_or("DB_URI", "postgresql://postgres:mysecretpassword@localhost:5432/postgres").replace("+psycopg", ""),
            max_connections: env_or_parse("DB_MAX_CONNECTIONS", 100),
            min_connections: env_or_parse("DB_MIN_CONNECTIONS", 5),
        }
    }
}

impl TwitchConfig {
    pub fn load() -> Self {
        TwitchConfig {
            client_id: env_required("TWITCH_CLIENT_ID").parse::<twitch_oauth2::ClientId>().expect("Invalid client id"),
            client_secret: env_required("TWITCH_CLIENT_SECRET").parse::<twitch_oauth2::ClientSecret>().expect("Invalid client secret"),
        }
    }
}

impl YouTubeConfig {
    pub fn load() -> Self {
        YouTubeConfig {
            api_key: env_required("YOUTUBE_API_KEY"),
        }
    }
}

impl DiscordConfig {
    pub fn load() -> Self {
        DiscordConfig {
            client_id: env_required("DISCORD_CLIENT_ID"),
            client_secret: env_required("DISCORD_CLIENT_SECRET"),
        }
    }
}
