#[cfg(feature = "database")]
use crate::entities::broadcaster;
#[cfg(feature = "database")]
use sea_orm::*;
use tracing::{info, warn, error, instrument, debug};

pub struct BroadcasterService {
    db: DatabaseConnection,
}

impl BroadcasterService {
    #[instrument(level = "debug")]
    pub fn new(db: DatabaseConnection) -> Self {
        debug!("Creating new BroadcasterService instance");
        Self { db }
    }

    /// Retrieves all broadcasters from the database.
    ///
    /// # Arguments
    ///
    /// * `include_hidden` - Optional include hidden broadcasters, otherwise excludes hidden broadcasters.
    #[instrument(level = "info", skip(self))]
    pub async fn get_all(&self, include_hidden: Option<bool>) -> Result<Vec<broadcaster::Model>, DbErr> {
        info!(include_hidden = ?include_hidden, "Fetching all broadcasters");

        let mut query = broadcaster::Entity::find();

        query = match include_hidden {
            Some(true) => {
                debug!("Including hidden broadcasters");
                query
            }
            Some(false) => {
                debug!("Excluding hidden broadcasters");
                query.filter(broadcaster::Column::Hidden.eq(false))
            }
            None => {
                debug!("Excluding hidden broadcasters by default");
                query.filter(broadcaster::Column::Hidden.eq(false))
            }
        };

        match query.all(&self.db).await {
            Ok(broadcasters) => {
                info!(broadcaster_count = broadcasters.len(), "Successfully fetched broadcasters");
                Ok(broadcasters)
            }
            Err(e) => {
                error!(error = %e, include_hidden = ?include_hidden, "Failed to fetch broadcasters");
                Err(e)
            }
        }
    }
}