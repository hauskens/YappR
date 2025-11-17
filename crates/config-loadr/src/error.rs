use std::fmt;

/// Errors that can occur during configuration loading
#[derive(Debug, Clone)]
pub enum ConfigError {
    /// A required environment variable is missing
    MissingEnvVar {
        key: String,
        description: String,
        example: Option<String>,
    },
    /// An environment variable has an invalid value
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

impl std::error::Error for ConfigError {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_missing_env_var_with_example() {
        let error = ConfigError::MissingEnvVar {
            key: "DATABASE_URL".to_string(),
            description: "PostgreSQL connection string".to_string(),
            example: Some("postgresql://user:pass@localhost/db".to_string()),
        };

        let output = error.to_string();
        assert!(output.contains("DATABASE_URL:"));
        assert!(output.contains("Description: PostgreSQL connection string"));
        assert!(output.contains("Example: DATABASE_URL=postgresql://user:pass@localhost/db"));
    }

    #[test]
    fn test_missing_env_var_without_example() {
        let error = ConfigError::MissingEnvVar {
            key: "SECRET_KEY".to_string(),
            description: "Secret encryption key".to_string(),
            example: None,
        };

        let output = error.to_string();
        assert!(output.contains("SECRET_KEY:"));
        assert!(output.contains("Description: Secret encryption key"));
        assert!(!output.contains("Example:"));
    }

    #[test]
    fn test_invalid_environment() {
        let error = ConfigError::InvalidEnvironment {
            key: "PORT".to_string(),
            value: "not-a-number".to_string(),
            description: "Must be a valid port number".to_string(),
        };

        let output = error.to_string();
        assert!(output.contains("PORT"));
        assert!(output.contains("Invalid value 'not-a-number'"));
        assert!(output.contains("Must be a valid port number"));
    }

    #[test]
    fn test_error_trait_implementation() {
        let error = ConfigError::MissingEnvVar {
            key: "TEST".to_string(),
            description: "Test var".to_string(),
            example: None,
        };

        // Verify it implements std::error::Error
        let _error_ref: &dyn std::error::Error = &error;
    }

    #[test]
    fn test_clone() {
        let error1 = ConfigError::MissingEnvVar {
            key: "TEST".to_string(),
            description: "Test var".to_string(),
            example: Some("example".to_string()),
        };

        let error2 = error1.clone();

        // Both should format the same way
        assert_eq!(error1.to_string(), error2.to_string());
    }

    #[test]
    fn test_debug_format() {
        let error = ConfigError::InvalidEnvironment {
            key: "ENV".to_string(),
            value: "test".to_string(),
            description: "Invalid environment".to_string(),
        };

        let debug_output = format!("{:?}", error);
        assert!(debug_output.contains("InvalidEnvironment"));
        assert!(debug_output.contains("ENV"));
    }
}
