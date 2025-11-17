pub mod builder;
pub mod environment;
pub mod error;
pub mod field;

// Re-export main types
pub use builder::{ConfigBuilder, env_or_default, env_or_option, env_parse, env_required};
pub use environment::Environment;
pub use error::ConfigError;
pub use field::ConfigField;

/// Initialize dotenv and load .env file if present
///
/// This is a convenience function that wraps dotenv::dotenv()
/// and suppresses errors if the .env file is not found.
pub fn load_dotenv() {
    let _ = dotenv::dotenv();
}
