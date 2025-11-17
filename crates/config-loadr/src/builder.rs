use crate::{error::ConfigError, field::ConfigField};
use std::{env, fmt, str::FromStr};
use tracing::{debug, instrument, warn};

/// Parse an environment variable into a specific type
#[instrument(level = "debug", skip(example))]
pub fn env_parse<'a, T: FromStr>(
    key: &str,
    description: &str,
    example: impl Into<Option<&'a str>>,
) -> Result<T, ConfigError> {
    let example = example.into();
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

/// Load a required environment variable, returning an error if missing or invalid
#[instrument(level = "debug", skip(example))]
pub fn env_required<T: FromStr>(
    key: &'static str,
    description: &'static str,
    example: impl Into<Option<&'static str>>,
) -> Result<ConfigField<T>, ConfigError> {
    let example = example.into();
    match env_parse(key, description, example) {
        Ok(value) => Ok(ConfigField::required(key, description, example, value)),
        Err(e) => Err(e),
    }
}

/// Load an optional environment variable with a default value
#[instrument(level = "debug", skip(example, default))]
pub fn env_or_default<T: FromStr>(
    key: &'static str,
    description: &'static str,
    example: impl Into<Option<&'static str>>,
    default: impl fmt::Display,
) -> ConfigField<T>
where
    <T as FromStr>::Err: std::fmt::Debug,
{
    let example = example.into();
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
    ConfigField::optional(key, description, example, value)
}

/// Load an optional environment variable, returning None if missing
#[instrument(level = "debug", skip(example))]
pub fn env_or_option<T: FromStr>(
    key: &'static str,
    description: &'static str,
    example: impl Into<Option<&'static str>>,
) -> ConfigField<Option<T>> {
    let example = example.into();
    let value = env_parse(key, description, example).ok();
    ConfigField::optional(key, description, example, value)
}

/// Helper to format multiple configuration errors into a panic message
pub fn format_config_errors(errors: &[ConfigError]) -> String {
    let error_summary = errors
        .iter()
        .map(|e| format!("  - {}", e))
        .collect::<Vec<_>>()
        .join("\n");
    format!(
        "Configuration failed with {} error(s):\n{}",
        errors.len(),
        error_summary
    )
}

/// A builder pattern for loading configuration with error collection
///
/// # Example
/// ```rust
/// use config_loadr::ConfigBuilder;
///
/// let mut builder = ConfigBuilder::new();
/// let port = builder.required::<u16>("PORT", "Server port", "8080");
///
/// builder.finish();
/// ```
pub struct ConfigBuilder {
    errors: Vec<ConfigError>,
}

impl ConfigBuilder {
    /// Create a new configuration builder
    pub fn new() -> Self {
        Self { errors: Vec::new() }
    }

    /// Load a required field, collecting errors if it fails
    pub fn required<T: FromStr>(
        &mut self,
        key: &'static str,
        description: &'static str,
        example: impl Into<Option<&'static str>>,
    ) -> Option<ConfigField<T>> {
        match env_required(key, description, example) {
            Ok(field) => Some(field),
            Err(e) => {
                self.errors.push(e);
                None
            }
        }
    }

    /// Load an optional field with a default value
    pub fn optional<T: FromStr>(
        &mut self,
        key: &'static str,
        description: &'static str,
        example: impl Into<Option<&'static str>>,
        default: impl fmt::Display,
    ) -> ConfigField<T>
    where
        <T as FromStr>::Err: std::fmt::Debug,
    {
        env_or_default(key, description, example, default)
    }

    /// Load an optional field that may be None
    pub fn optional_none<T: FromStr>(
        &mut self,
        key: &'static str,
        description: &'static str,
        example: impl Into<Option<&'static str>>,
    ) -> ConfigField<Option<T>> {
        env_or_option(key, description, example)
    }

    /// Load a required field, collecting errors if it fails, and return self for chaining
    ///
    /// This method allows for fluent chaining but discards the loaded value.
    /// Use the non-chaining `required()` method if you need the value immediately.
    ///
    /// # Example
    /// ```no_run
    /// use config_loadr::ConfigBuilder;
    ///
    /// let mut builder = ConfigBuilder::new();
    /// builder.with_required::<u16>("PORT", "Server port", "8080");
    /// builder.finish_or_panic();
    /// ```
    pub fn with_required<T: FromStr>(
        &mut self,
        key: &'static str,
        description: &'static str,
        example: impl Into<Option<&'static str>>,
    ) -> &mut Self {
        match env_required::<T>(key, description, example) {
            Ok(_) => {}
            Err(e) => {
                self.errors.push(e);
            }
        }
        self
    }

    /// Load an optional field with a default value and return self for chaining
    ///
    /// This method validates that the environment variable can be parsed but discards the value.
    /// Use the non-chaining `optional()` method if you need the value immediately.
    ///
    /// # Example
    /// ```
    /// use config_loadr::ConfigBuilder;
    ///
    /// let mut builder = ConfigBuilder::new();
    /// builder.with_optional::<u16>("PORT", "Server port", "8080", 8080);
    /// builder.finish_or_panic();
    /// ```
    pub fn with_optional<T: FromStr>(
        &mut self,
        key: &'static str,
        description: &'static str,
        example: impl Into<Option<&'static str>>,
        default: impl fmt::Display,
    ) -> &mut Self
    where
        <T as FromStr>::Err: std::fmt::Debug,
    {
        // Just validate, don't store
        let _: ConfigField<T> = env_or_default(key, description, example, default);
        self
    }

    /// Load an optional field that may be None and return self for chaining
    ///
    /// This method validates that the environment variable can be parsed but discards the value.
    /// Use the non-chaining `optional_none()` method if you need the value immediately.
    ///
    /// # Example
    /// ```
    /// use config_loadr::ConfigBuilder;
    ///
    /// let mut builder = ConfigBuilder::new();
    /// builder.with_optional_none::<String>("API_KEY", "Optional API key", "sk-...");
    /// builder.finish_or_panic();
    /// ```
    pub fn with_optional_none<T: FromStr>(
        &mut self,
        key: &'static str,
        description: &'static str,
        example: impl Into<Option<&'static str>>,
    ) -> &mut Self {
        // Just validate, don't store
        let _: ConfigField<Option<T>> = env_or_option(key, description, example);
        self
    }

    /// Finish building and return any errors that were collected
    pub fn finish(self) -> Result<(), Vec<ConfigError>> {
        if self.errors.is_empty() {
            Ok(())
        } else {
            Err(self.errors)
        }
    }

    /// Finish building and panic if there were any errors
    pub fn finish_or_panic(self) {
        if !self.errors.is_empty() {
            panic!("{}", format_config_errors(&self.errors));
        }
    }
}

impl Default for ConfigBuilder {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_builder_new() {
        let builder = ConfigBuilder::new();
        assert_eq!(builder.errors.len(), 0);
    }

    #[test]
    fn test_builder_default() {
        let builder = ConfigBuilder::default();
        assert_eq!(builder.errors.len(), 0);
    }

    #[test]
    fn test_builder_finish_with_no_errors() {
        let builder = ConfigBuilder::new();
        let result = builder.finish();
        assert!(result.is_ok());
    }

    #[test]
    fn test_builder_collects_errors() {
        let mut builder = ConfigBuilder::new();

        // Manually add errors to simulate failed required fields
        builder.errors.push(ConfigError::MissingEnvVar {
            key: "MISSING_VAR".to_string(),
            description: "Test variable".to_string(),
            example: None,
        });

        let result = builder.finish();
        assert!(result.is_err());

        if let Err(errors) = result {
            assert_eq!(errors.len(), 1);
        }
    }

    #[test]
    fn test_builder_collects_multiple_errors() {
        let mut builder = ConfigBuilder::new();

        builder.errors.push(ConfigError::MissingEnvVar {
            key: "VAR1".to_string(),
            description: "First variable".to_string(),
            example: None,
        });

        builder.errors.push(ConfigError::MissingEnvVar {
            key: "VAR2".to_string(),
            description: "Second variable".to_string(),
            example: None,
        });

        let result = builder.finish();
        assert!(result.is_err());

        if let Err(errors) = result {
            assert_eq!(errors.len(), 2);
        }
    }

    #[test]
    fn test_format_config_errors_single() {
        let errors = vec![ConfigError::MissingEnvVar {
            key: "TEST_VAR".to_string(),
            description: "Test variable".to_string(),
            example: Some("example".to_string()),
        }];

        let formatted = format_config_errors(&errors);
        assert!(formatted.contains("Configuration failed with 1 error(s)"));
        assert!(formatted.contains("TEST_VAR"));
    }

    #[test]
    fn test_format_config_errors_multiple() {
        let errors = vec![
            ConfigError::MissingEnvVar {
                key: "VAR1".to_string(),
                description: "First".to_string(),
                example: None,
            },
            ConfigError::InvalidEnvironment {
                key: "VAR2".to_string(),
                value: "bad".to_string(),
                description: "Second".to_string(),
            },
        ];

        let formatted = format_config_errors(&errors);
        assert!(formatted.contains("Configuration failed with 2 error(s)"));
        assert!(formatted.contains("VAR1"));
        assert!(formatted.contains("VAR2"));
    }

    #[test]
    #[should_panic(expected = "Configuration failed")]
    fn test_finish_or_panic_panics() {
        let mut builder = ConfigBuilder::new();

        builder.errors.push(ConfigError::MissingEnvVar {
            key: "MISSING".to_string(),
            description: "Test".to_string(),
            example: None,
        });

        builder.finish_or_panic();
    }

    #[test]
    fn test_finish_or_panic_succeeds() {
        let builder = ConfigBuilder::new();
        builder.finish_or_panic();
    }

    #[test]
    fn test_config_field_metadata_preserved() {
        // Test that ConfigField created by helpers has correct metadata
        let field = ConfigField::required("TEST_KEY", "Test description", Some("example"), 123);

        assert_eq!(field.key, "TEST_KEY");
        assert_eq!(field.description, "Test description");
        assert_eq!(field.example, Some("example"));
        assert!(field.required);
        assert_eq!(field.value, 123);
    }

    #[test]
    fn test_optional_field_metadata() {
        let field = ConfigField::optional("OPT_KEY", "Optional key", None, "default");

        assert_eq!(field.key, "OPT_KEY");
        assert_eq!(field.description, "Optional key");
        assert_eq!(field.example, None);
        assert!(!field.required);
        assert_eq!(field.value, "default");
    }

    // Tests for chainable methods
    #[test]
    fn test_chaining_returns_mutable_reference() {
        let mut builder = ConfigBuilder::new();

        // Test that chaining returns &mut Self
        let builder_ref = builder
            .with_optional::<u16>("PORT", "Server port", "8080", 8080)
            .with_optional::<String>("HOST", "Server host", "localhost", "localhost");

        // Should be able to call more methods on the reference
        builder_ref.with_optional::<bool>("DEBUG", "Debug mode", "false", false);

        // Builder should have no errors from optional fields
        assert_eq!(builder.errors.len(), 0);
    }

    #[test]
    fn test_chaining_finish_no_errors() {
        let mut builder = ConfigBuilder::new();
        builder.with_optional::<u16>("PORT", "Server port", "8080", 8080);

        let result = builder.finish();
        assert!(result.is_ok());
    }

    #[test]
    fn test_chaining_finish_or_panic_no_errors() {
        let mut builder = ConfigBuilder::new();
        builder.with_optional::<u16>("PORT", "Server port", "8080", 8080);

        builder.finish_or_panic();
        // Should not panic
    }

    #[test]
    fn test_mixed_chaining_and_direct_methods() {
        let mut builder = ConfigBuilder::new();

        // Use chaining methods
        builder
            .with_optional::<u16>("PORT", "Server port", "8080", 8080)
            .with_optional_none::<String>("API_KEY", "Optional API key", "sk-...");

        // Can still call non-chaining methods
        let port: ConfigField<u32> = builder.optional("MAX_CONN", "Max connections", "100", 100);
        assert_eq!(*port, 100);

        assert_eq!(builder.errors.len(), 0);
    }

    #[test]
    fn test_chaining_allows_fluent_api() {
        // This test demonstrates the fluent API pattern
        let mut builder = ConfigBuilder::new();

        builder
            .with_optional::<u16>("PORT", "Server port", "8080", 8080)
            .with_optional::<String>("HOST", "Host address", "0.0.0.0", "0.0.0.0")
            .with_optional_none::<String>("API_KEY", "Optional API key", None);

        let result = builder.finish();
        assert!(result.is_ok());
    }

    #[test]
    fn test_chaining_can_be_assigned() {
        let mut builder = ConfigBuilder::new();
        let builder_ref = builder.with_optional::<u16>("PORT", "Server port", "8080", 8080);

        // The reference can be used further
        builder_ref.with_optional::<String>("HOST", "Host address", "localhost", "localhost");

        assert_eq!(builder.errors.len(), 0);
    }
}
