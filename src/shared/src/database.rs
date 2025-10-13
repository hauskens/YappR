use sea_orm::{Database, DatabaseConnection, ConnectOptions};
use crate::config::Config;
use tracing::{info, error, instrument, debug};

#[instrument(level = "info")]
pub async fn get_database_connection() -> Result<DatabaseConnection, sea_orm::DbErr> {
    info!("Establishing database connection");
    let config = Config::load();

    let mut opt = ConnectOptions::new(config.database.url);
    opt.max_connections(config.database.max_connections)
        .min_connections(config.database.min_connections)
        .sqlx_logging(true);

    debug!(
        max_connections = config.database.max_connections,
        min_connections = config.database.min_connections,
        sqlx_logging = true,
        "Database connection options configured"
    );

    match Database::connect(opt).await {
        Ok(connection) => {
            info!("Database connection established successfully");
            Ok(connection)
        }
        Err(e) => {
            error!(error = %e, "Failed to establish database connection");
            Err(e)
        }
    }
}