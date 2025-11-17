use std::ops::Deref;

/// A configuration field with metadata and value
#[derive(Debug, Clone)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct ConfigField<T> {
    /// Environment variable key
    pub key: &'static str,
    /// Human-readable description of what this config does
    pub description: &'static str,
    /// Example value for documentation/error messages
    pub example: Option<&'static str>,
    /// Whether this field is required (true) or optional with a default (false)
    pub required: bool,
    /// The actual configuration value
    pub value: T,
}

impl<T> ConfigField<T> {
    /// Create a new required config field
    pub fn required(
        key: &'static str,
        description: &'static str,
        example: impl Into<Option<&'static str>>,
        value: T,
    ) -> Self {
        Self {
            key,
            description,
            example: example.into(),
            required: true,
            value,
        }
    }

    /// Create a new optional config field with a default value
    pub fn optional(
        key: &'static str,
        description: &'static str,
        example: impl Into<Option<&'static str>>,
        value: T,
    ) -> Self {
        Self {
            key,
            description,
            example: example.into(),
            required: false,
            value,
        }
    }

    // /// Map the inner value to a different type
    // pub fn map<U, F>(self, f: F) -> ConfigField<U>
    // where
    //     F: FnOnce(T) -> U,
    // {
    //     ConfigField {
    //         key: self.key,
    //         description: self.description,
    //         example: self.example,
    //         required: self.required,
    //         value: f(self.value),
    //     }
    // }
}

// Allow using ConfigField<T> as &T without writing .value
impl<T> Deref for ConfigField<T> {
    type Target = T;

    fn deref(&self) -> &Self::Target {
        &self.value
    }
}

// Allow using ConfigField<T> as &T via AsRef
impl<T> AsRef<T> for ConfigField<T> {
    fn as_ref(&self) -> &T {
        &self.value
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_required_field_creation() {
        let field = ConfigField::required("PORT", "Server port", Some("8080"), 8080u16);

        assert_eq!(field.key, "PORT");
        assert_eq!(field.description, "Server port");
        assert_eq!(field.example, Some("8080"));
        assert!(field.required);
        assert_eq!(field.value, 8080);
        assert_eq!(*field, 8080);
    }

    #[test]
    fn test_optional_field_creation() {
        let field = ConfigField::optional("DEBUG", "Debug mode", Some("true"), false);

        assert_eq!(field.key, "DEBUG");
        assert_eq!(field.description, "Debug mode");
        assert_eq!(field.example, Some("true"));
        assert!(!field.required);
        assert!(!field.value);
        assert!(!(*field));
    }

    #[test]
    fn test_field_without_example() {
        let field = ConfigField::required("SECRET", "Secret key", None, "secret-value");

        assert_eq!(field.example, None);
        assert_eq!(field.value, "secret-value");
        assert_eq!(*field, "secret-value");
    }

    #[test]
    fn test_deref_implementation() {
        let field = ConfigField::required("PORT", "Server port", Some("8080"), 8080u16);

        // Should be able to use * to access value
        assert_eq!(*field, 8080);

        // Should be able to call methods on the dereferenced value
        let doubled = *field * 2;
        assert_eq!(doubled, 16160);
    }

    #[test]
    fn test_as_ref_implementation() {
        let field = ConfigField::required(
            "NAME",
            "Service name",
            Some("my-service"),
            "test-service".to_string(),
        );

        // Should be able to use as_ref() to get a reference
        let name_ref: &String = field.as_ref();
        assert_eq!(name_ref, "test-service");
    }
}
