use crate::config::Environment;
use semver::Version;
use tracing_subscriber::{EnvFilter, layer::SubscriberExt, util::SubscriberInitExt};

/// Initialize logging with optional Loki integration
///
/// # Arguments
/// * `service_name` - Name of the service for Loki labels
/// * `loki_url` - Optional Loki URL for remote logging
/// * `version` - Service version for Loki labels
/// * `environment` - Environment name for Loki labels
///
/// # Behavior
/// - If `loki_url` is provided: Sets up dual output (console + Loki)
/// - If `loki_url` is None: Sets up console-only logging
/// - Respects RUST_LOG environment variable
/// - Default filter: See `get_default_env_filter()` for default rules
pub fn init_logging(
    service_name: &str,
    loki_url: Option<url::Url>,
    version: Version,
    environment: Environment,
) {
    if let Some(loki_url) = loki_url {
        init_with_loki(service_name, loki_url, version, environment);
    } else {
        init_console_only();
    }
}

/// Creates the default environment filter with logging rules
///
/// Default rules:
/// - `info` - Default log level for all modules
/// - `sqlx::query=warn` - Suppress noisy SQL query logs
///
/// Example additional rules you can add:
/// - `serenity::client=warn` - Reduce Discord client logs
/// - `twitch_api=warn` - Reduce Twitch API logs
/// - `yappr_bot::discord::message_handler=debug` - Enable debug for specific module
///
/// To override at runtime, set the RUST_LOG environment variable:
/// ```bash
/// RUST_LOG=debug cargo run
/// RUST_LOG=warn,yappr_bot::twitch=debug cargo run
/// ```
fn get_default_env_filter() -> EnvFilter {
    EnvFilter::try_from_default_env().unwrap_or_else(|_| {
        EnvFilter::new(
            "info,\
             sqlx::query=warn,\
             subscriber::handle_message=warn",
        )
    })
}

#[cfg(feature = "loki")]
fn init_with_loki(
    service_name: &str,
    loki_url: url::Url,
    version: Version,
    environment: Environment,
) {
    let env_filter = get_default_env_filter();

    match tracing_loki::builder()
        .label("service", service_name)
        .and_then(|b| b.label("version", version.to_string()))
        .and_then(|b| b.label("environment", environment.to_string()))
        .and_then(|b| b.build_url(loki_url.clone()))
    {
        Ok((layer, task)) => {
            // Add both Loki and console output for visibility
            tracing_subscriber::registry()
                .with(layer)
                .with(env_filter)
                .with(tracing_subscriber::fmt::layer())
                .init();

            // Spawn the log flushing task
            tokio::spawn(task);

            eprintln!("✓ Loki logging configured successfully (dual output: console + Loki)");

            tracing::info!(
                task = "tracing_setup",
                result = "success",
                loki_url = %loki_url,
                service = service_name,
                "Logging configured with Loki",
            );
        }
        Err(e) => {
            eprintln!("✗ Failed to configure Loki: {}", e);
            eprintln!("  Falling back to console-only logging");

            let env_filter = get_default_env_filter();

            // Fallback to console logging
            tracing_subscriber::registry()
                .with(env_filter)
                .with(tracing_subscriber::fmt::layer())
                .init();

            tracing::warn!(
                task = "tracing_setup",
                result = "fallback",
                error = %e,
                "Failed to configure Loki, using console logging",
            );
        }
    }
}

#[cfg(not(feature = "loki"))]
fn init_with_loki(
    _service_name: &str,
    _loki_url: url::Url,
    _version: Version,
    _environment: Environment,
) {
    eprintln!("Loki feature not enabled, falling back to console-only logging");
    init_console_only();
}

fn init_console_only() {
    eprintln!("No LOKI_URL configured, using console-only logging");

    let env_filter = get_default_env_filter();

    tracing_subscriber::registry()
        .with(env_filter)
        .with(tracing_subscriber::fmt::layer())
        .init();

    tracing::info!(
        task = "tracing_setup",
        result = "success",
        "Logging configured with console output",
    );
}
