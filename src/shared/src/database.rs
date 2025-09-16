use sea_orm::{Database, DatabaseConnection, ConnectOptions};
use std::env;

pub async fn get_database_connection() -> Result<DatabaseConnection, sea_orm::DbErr> {
    let database_url = env::var("DB_URI").unwrap_or_else(|_| 
        "postgresql://postgres:mysecretpassword@postgres-db:5432/postgres".to_string()
    ).replace("+psycopg", "");
    
    let mut opt = ConnectOptions::new(database_url);
    opt.max_connections(100)
        .min_connections(5)
        .sqlx_logging(true);
    
    Database::connect(opt).await
}