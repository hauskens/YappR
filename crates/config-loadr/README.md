# config-loadr

A type-safe, developer-friendly configuration loading library for Rust applications.

## Features

- **Type-safe**: Uses Rust's type system to ensure configuration values are valid
- **Helpful errors**: Clear error messages with descriptions and examples
- **Metadata tracking**: Each config field includes key, description, and example
- **Flexible loading**: Support for required, optional, and default values
- **Error collection**: Load all config at once and collect all errors
- **Dotenv support**: Automatically loads .env files

## Basic Usage

```rust
use config_loadr::{ConfigField, env_or_default, env_required};

// Load a required config value
let database_url = env_required::<String>(
    "DATABASE_URL",
    "PostgreSQL connection string",
    "postgresql://user:password@localhost/db",
)?;

// Load an optional value with a default
let port = env_or_default(
    "PORT",
    "Server port",
    "8080",
    8080,
);

// Access the value directly (ConfigField implements Deref)
println!("Server running on port {}", *port);
```

## Using the ConfigBuilder

For complex configurations with many fields, use `ConfigBuilder` to collect all errors:

```rust
use config_loadr::ConfigBuilder;

let mut builder = ConfigBuilder::new();

let db_url = builder.required::<String>(
    "DATABASE_URL",
    "PostgreSQL connection string",
    "postgresql://...",
);
let max_connections = builder.optional(
    "MAX_CONNECTIONS",
    "Maximum database connections",
    "100",
    100,
);
let api_key = builder.optional_none::<String>(
    "API_KEY",
    "Optional API key for external service",
    "sk-...",
);

// Check if all required fields were loaded successfully
builder.finish_or_panic();

// Now you can safely unwrap the required fields
let db_url = db_url.unwrap();
```

### Chainable Builder Pattern

For a more fluent API, use the chainable `with_*` methods:

```rust
use config_loadr::ConfigBuilder;

// Chainable methods validate config but don't return values
// Use them for validation-only scenarios
ConfigBuilder::new()
    .with_optional("PORT", "Server port", "8080", 8080u16)
    .with_optional("MAX_CONNECTIONS", "Maximum database connections", "100", 100)
    .with_optional_none::<String>("API_KEY", "Optional API key", "sk-...")
    .finish_or_panic();
```

The chainable methods return `&mut Self` for fluent chaining:
- `with_required<T>()` - Validate a required field, collect errors if missing
- `with_optional<T>()` - Validate an optional field with a default value
- `with_optional_none<T>()` - Validate an optional field that may be None

If you need the values, use the non-chaining methods (`required()`, `optional()`, `optional_none()`), or combine both approaches:

```rust
let mut builder = ConfigBuilder::new();

// Get values using non-chaining methods
let port = builder.optional("PORT", "Server port", "8080", 8080u16);

// Validate other fields with chaining
builder
    .with_optional_none::<String>("API_KEY", "API key", "sk-...")
    .finish_or_panic();

println!("Server running on port {}", *port);
```

## Environment Enum

The library provides a built-in `Environment` enum for common runtime environments:

```rust
use config_loadr::{Environment, env_required};

let env = env_required::<Environment>(
    "ENVIRONMENT",
    "Runtime environment",
    "prod",
)?;

if env.is_prod() {
    // Production-specific logic
}
```

Supported values: `dev`, `development`, `staging`, `stage`, `prod`, `production`

## ConfigField Structure

Each configuration field contains:

```rust
pub struct ConfigField<T> {
    pub key: &'static str,        // Environment variable name
    pub description: &'static str, // Human-readable description
    pub example: Option<&'static str>, // Example value
    pub required: bool,            // Whether this field is required
    pub value: T,                  // The actual value
}
```

You can create fields manually:

```rust
use config_loadr::ConfigField;

let field = ConfigField::required(
    "API_KEY",
    "Authentication key",
    "sk-...",
    "actual-key-value".to_string(),
);

let optional_field = ConfigField::optional(
    "DEBUG",
    "Enable debug mode",
    "true",
    false,
);

// If you don't want to provide an example, use None
let field_no_example = ConfigField::required(
    "SECRET_KEY",
    "Secret key for encryption",
    None,
    "secret-value".to_string(),
);
```

## Error Handling

The library provides detailed error messages:

```
DATABASE_URL:
    Description: PostgreSQL connection string
    Example: DATABASE_URL=postgresql://user:password@localhost/db
```

## Features

- `serde`: Enable serialization/deserialization support for ConfigField and Environment

```toml
[dependencies]
config-loadr = { version = "*", features = ["serde"] }
```

## License

This library is part of the YappR project.
