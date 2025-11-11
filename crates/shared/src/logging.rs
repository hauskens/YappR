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
/// - Default filter: "info,sqlx::query=warn" (suppresses noisy SQL logs)
pub fn init_logging(
    service_name: &str,
    loki_url: Option<url::Url>,
    version: &str,
    environment: &str,
) {
    if let Some(loki_url) = loki_url {
        init_with_loki(service_name, loki_url, version, environment);
    } else {
        init_console_only();
    }
}

#[cfg(feature = "loki")]
fn init_with_loki(service_name: &str, loki_url: url::Url, version: &str, environment: &str) {
    eprintln!("Setting up Loki logging...");
    eprintln!("  URL: {}", loki_url);
    eprintln!("  Service: {}", service_name);
    eprintln!("  Environment: {}", environment);

    match tracing_loki::builder()
        .label("service", service_name)
        .and_then(|b| b.label("version", version))
        .and_then(|b| b.label("environment", environment))
        .and_then(|b| b.build_url(loki_url.clone()))
    {
        Ok((layer, task)) => {
            // Add both Loki and console output for visibility
            tracing_subscriber::registry()
                .with(layer)
                .with(
                    EnvFilter::try_from_default_env()
                        .unwrap_or_else(|_| EnvFilter::new("info,sqlx::query=warn")),
                )
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

            // Fallback to console logging
            tracing_subscriber::registry()
                .with(
                    EnvFilter::try_from_default_env()
                        .unwrap_or_else(|_| EnvFilter::new("info,sqlx::query=warn")),
                )
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
fn init_with_loki(_service_name: &str, _loki_url: url::Url, _version: &str, _environment: &str) {
    eprintln!("Loki feature not enabled, falling back to console-only logging");
    init_console_only();
}

fn init_console_only() {
    eprintln!("No LOKI_URL configured, using console-only logging");

    tracing_subscriber::registry()
        .with(
            EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| EnvFilter::new("info,sqlx::query=warn")),
        )
        .with(tracing_subscriber::fmt::layer())
        .init();

    tracing::info!(
        task = "tracing_setup",
        result = "success",
        "Logging configured with console output",
    );
}
