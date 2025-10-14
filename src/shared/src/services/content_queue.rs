use sea_orm::{DatabaseConnection, EntityTrait, QueryFilter, ColumnTrait, QueryOrder, QuerySelect, DbErr};
use crate::entities::{prelude::*, content_queue};
use tracing::{info, instrument};

/// Simple content queue service for basic CRUD operations (no authorization)
pub struct ContentQueueService;

impl ContentQueueService {
    /// Get all queue entries from the database
    #[instrument(level = "info", skip(db))]
    pub async fn get_all(db: &DatabaseConnection) -> Result<Vec<content_queue::Model>, DbErr> {
        info!("Fetching all queue entries");

        let entries = ContentQueue::find()
            .all(db)
            .await?;

        info!(count = entries.len(), "Retrieved queue entries");
        Ok(entries)
    }

    /// Get a queue entry by its ID
    #[instrument(level = "info", skip(db))]
    pub async fn get_by_id(db: &DatabaseConnection, id: i32) -> Result<Option<content_queue::Model>, DbErr> {
        info!(queue_id = id, "Fetching queue entry by ID");

        let entry = ContentQueue::find_by_id(id)
            .one(db)
            .await?;

        match &entry {
            Some(_) => info!(queue_id = id, "Queue entry found"),
            None => info!(queue_id = id, "Queue entry not found"),
        }

        Ok(entry)
    }

    /// Get all queue entries for a specific broadcaster
    #[instrument(level = "info", skip(db))]
    pub async fn get_by_broadcaster(db: &DatabaseConnection, broadcaster_id: i32) -> Result<Vec<content_queue::Model>, DbErr> {
        info!(broadcaster_id = broadcaster_id, "Fetching queue entries for broadcaster");

        let entries = ContentQueue::find()
            .filter(content_queue::Column::BroadcasterId.eq(broadcaster_id))
            .all(db)
            .await?;

        info!(broadcaster_id = broadcaster_id, count = entries.len(), "Retrieved queue entries for broadcaster");
        Ok(entries)
    }

    /// Get unwatched queue entries for a broadcaster
    #[instrument(level = "info", skip(db))]
    pub async fn get_unwatched(db: &DatabaseConnection, broadcaster_id: i32) -> Result<Vec<content_queue::Model>, DbErr> {
        info!(broadcaster_id = broadcaster_id, "Fetching unwatched queue entries");

        let entries = ContentQueue::find()
            .filter(content_queue::Column::BroadcasterId.eq(broadcaster_id))
            .filter(content_queue::Column::Watched.eq(false))
            .filter(content_queue::Column::Skipped.eq(false))
            .filter(content_queue::Column::Disabled.eq(false))
            .all(db)
            .await?;

        info!(broadcaster_id = broadcaster_id, count = entries.len(), "Retrieved unwatched queue entries");
        Ok(entries)
    }

    /// Get watched queue entries for a broadcaster
    #[instrument(level = "info", skip(db))]
    pub async fn get_watched(db: &DatabaseConnection, broadcaster_id: i32) -> Result<Vec<content_queue::Model>, DbErr> {
        info!(broadcaster_id = broadcaster_id, "Fetching watched queue entries");

        let entries = ContentQueue::find()
            .filter(content_queue::Column::BroadcasterId.eq(broadcaster_id))
            .filter(content_queue::Column::Watched.eq(true))
            .all(db)
            .await?;

        info!(broadcaster_id = broadcaster_id, count = entries.len(), "Retrieved watched queue entries");
        Ok(entries)
    }

    /// Get top scored queue entries for a broadcaster (sorted by score descending)
    #[instrument(level = "info", skip(db))]
    pub async fn get_top_scored(db: &DatabaseConnection, broadcaster_id: i32, limit: u64) -> Result<Vec<content_queue::Model>, DbErr> {
        info!(broadcaster_id = broadcaster_id, limit = limit, "Fetching top scored queue entries");

        let entries = ContentQueue::find()
            .filter(content_queue::Column::BroadcasterId.eq(broadcaster_id))
            .filter(content_queue::Column::Watched.eq(false))
            .filter(content_queue::Column::Skipped.eq(false))
            .filter(content_queue::Column::Disabled.eq(false))
            .order_by_desc(content_queue::Column::Score)
            .limit(limit)
            .all(db)
            .await?;

        info!(broadcaster_id = broadcaster_id, limit = limit, count = entries.len(), "Retrieved top scored queue entries");
        Ok(entries)
    }

    /// Get queue entries for a specific content item
    #[instrument(level = "info", skip(db))]
    pub async fn get_by_content(db: &DatabaseConnection, content_id: i32) -> Result<Vec<content_queue::Model>, DbErr> {
        info!(content_id = content_id, "Fetching queue entries for content");

        let entries = ContentQueue::find()
            .filter(content_queue::Column::ContentId.eq(content_id))
            .all(db)
            .await?;

        info!(content_id = content_id, count = entries.len(), "Retrieved queue entries for content");
        Ok(entries)
    }

    /// Get skipped queue entries for a broadcaster
    #[instrument(level = "info", skip(db))]
    pub async fn get_skipped(db: &DatabaseConnection, broadcaster_id: i32) -> Result<Vec<content_queue::Model>, DbErr> {
        info!(broadcaster_id = broadcaster_id, "Fetching skipped queue entries");

        let entries = ContentQueue::find()
            .filter(content_queue::Column::BroadcasterId.eq(broadcaster_id))
            .filter(content_queue::Column::Skipped.eq(true))
            .all(db)
            .await?;

        info!(broadcaster_id = broadcaster_id, count = entries.len(), "Retrieved skipped queue entries");
        Ok(entries)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    #[ignore] // Requires database connection
    async fn test_get_all_queue_entries() {
        // Example test structure
        // let db = get_test_database_connection().await.unwrap();
        // let entries = ContentQueueService::get_all(&db).await.unwrap();
        // assert!(entries.len() >= 0);
    }
}
