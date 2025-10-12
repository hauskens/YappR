use sea_orm::{Database, DatabaseConnection, ConnectOptions};
use crate::config::Config;

pub async fn get_database_connection() -> Result<DatabaseConnection, sea_orm::DbErr> {
    let config = Config::load();
    
    let mut opt = ConnectOptions::new(config.database.url);
    opt.max_connections(100)
        .min_connections(5)
        .sqlx_logging(true);
    
    Database::connect(opt).await
}