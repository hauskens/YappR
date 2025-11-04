use crate::entities::{broadcaster, prelude::*};
use sea_orm::{ColumnTrait, DatabaseConnection, DbErr, EntityTrait, QueryFilter};
use tracing::{info, instrument};

/// Simple broadcaster service for basic CRUD operations (no authorization)
pub struct BroadcasterService;

impl BroadcasterService {
    /// Get all broadcasters from the database
    #[instrument(level = "info", skip(db))]
    pub async fn get_all(db: &DatabaseConnection) -> Result<Vec<broadcaster::Model>, DbErr> {
        info!("Fetching all broadcasters");

        let broadcasters = Broadcaster::find().all(db).await?;

        info!(count = broadcasters.len(), "Retrieved broadcasters");
        Ok(broadcasters)
    }

    /// Get a broadcaster by its ID
    #[instrument(level = "info", skip(db))]
    pub async fn get_by_id(
        db: &DatabaseConnection,
        id: i32,
    ) -> Result<Option<broadcaster::Model>, DbErr> {
        info!(broadcaster_id = id, "Fetching broadcaster by ID");

        let broadcaster = Broadcaster::find_by_id(id).one(db).await?;

        match &broadcaster {
            Some(_) => info!(broadcaster_id = id, "Broadcaster found"),
            None => info!(broadcaster_id = id, "Broadcaster not found"),
        }

        Ok(broadcaster)
    }

    /// Get a broadcaster by its unique name
    #[instrument(level = "info", skip(db))]
    pub async fn get_by_name(
        db: &DatabaseConnection,
        name: &str,
    ) -> Result<Option<broadcaster::Model>, DbErr> {
        info!(broadcaster_name = name, "Fetching broadcaster by name");

        let broadcaster = Broadcaster::find()
            .filter(broadcaster::Column::Name.eq(name))
            .one(db)
            .await?;

        match &broadcaster {
            Some(b) => info!(
                broadcaster_id = b.id,
                broadcaster_name = name,
                "Broadcaster found"
            ),
            None => info!(broadcaster_name = name, "Broadcaster not found"),
        }

        Ok(broadcaster)
    }

    /// Get all visible (non-hidden) broadcasters
    #[instrument(level = "info", skip(db))]
    pub async fn get_visible(db: &DatabaseConnection) -> Result<Vec<broadcaster::Model>, DbErr> {
        info!("Fetching visible broadcasters");

        let broadcasters = Broadcaster::find()
            .filter(broadcaster::Column::Hidden.eq(false))
            .all(db)
            .await?;

        info!(count = broadcasters.len(), "Retrieved visible broadcasters");
        Ok(broadcasters)
    }

    /// Get all hidden broadcasters
    #[instrument(level = "info", skip(db))]
    pub async fn get_hidden(db: &DatabaseConnection) -> Result<Vec<broadcaster::Model>, DbErr> {
        info!("Fetching hidden broadcasters");

        let broadcasters = Broadcaster::find()
            .filter(broadcaster::Column::Hidden.eq(true))
            .all(db)
            .await?;

        info!(count = broadcasters.len(), "Retrieved hidden broadcasters");
        Ok(broadcasters)
    }
}
