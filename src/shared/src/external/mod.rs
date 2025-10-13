#[cfg(any(feature = "twitch", feature = "youtube"))]
pub mod api_client;
#[cfg(feature = "twitch")]
pub mod twitch;
#[cfg(feature = "youtube")]
pub mod youtube;

// Re-export all api_client types and traits
#[cfg(any(feature = "twitch", feature = "youtube"))]
pub use api_client::*;

// Re-export individual platform clients with their ApiClient implementations
#[cfg(feature = "twitch")]
pub use twitch::TwitchApiClient;
#[cfg(feature = "youtube")]
pub use youtube::YouTubeApiClient;
