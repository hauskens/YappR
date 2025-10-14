use sea_orm::{DatabaseConnection, EntityTrait, QueryFilter, ColumnTrait, QueryOrder, QuerySelect, DbErr};
use crate::entities::{prelude::*, content};
use tracing::{info, instrument};

/// Simple content service for basic CRUD operations (no authorization)
pub struct ContentService;

impl ContentService {
    /// Get all content from the database
    #[instrument(level = "info", skip(db))]
    pub async fn get_all(db: &DatabaseConnection) -> Result<Vec<content::Model>, DbErr> {
        info!("Fetching all content");

        let content_list = Content::find()
            .all(db)
            .await?;

        info!(count = content_list.len(), "Retrieved content");
        Ok(content_list)
    }

    /// Get content by its ID
    #[instrument(level = "info", skip(db))]
    pub async fn get_by_id(db: &DatabaseConnection, id: i32) -> Result<Option<content::Model>, DbErr> {
        info!(content_id = id, "Fetching content by ID");

        let content = Content::find_by_id(id)
            .one(db)
            .await?;

        match &content {
            Some(_) => info!(content_id = id, "Content found"),
            None => info!(content_id = id, "Content not found"),
        }

        Ok(content)
    }

    /// Get content by stripped URL
    #[instrument(level = "info", skip(db))]
    pub async fn get_by_stripped_url(db: &DatabaseConnection, stripped_url: &str) -> Result<Option<content::Model>, DbErr> {
        info!(stripped_url = stripped_url, "Fetching content by stripped URL");

        let content = Content::find()
            .filter(content::Column::StrippedUrl.eq(stripped_url))
            .one(db)
            .await?;

        match &content {
            Some(c) => info!(content_id = c.id, stripped_url = stripped_url, "Content found"),
            None => info!(stripped_url = stripped_url, "Content not found"),
        }

        Ok(content)
    }

    /// Get content by author
    #[instrument(level = "info", skip(db))]
    pub async fn get_by_author(db: &DatabaseConnection, author: &str) -> Result<Vec<content::Model>, DbErr> {
        info!(author = author, "Fetching content by author");

        let content_list = Content::find()
            .filter(content::Column::Author.eq(author))
            .all(db)
            .await?;

        info!(author = author, count = content_list.len(), "Retrieved content by author");
        Ok(content_list)
    }

    /// Get content by channel name
    #[instrument(level = "info", skip(db))]
    pub async fn get_by_channel_name(db: &DatabaseConnection, channel_name: &str) -> Result<Vec<content::Model>, DbErr> {
        info!(channel_name = channel_name, "Fetching content by channel name");

        let content_list = Content::find()
            .filter(content::Column::ChannelName.eq(channel_name))
            .all(db)
            .await?;

        info!(channel_name = channel_name, count = content_list.len(), "Retrieved content by channel");
        Ok(content_list)
    }

    /// Get recent content (ordered by created_at, limited by count)
    #[instrument(level = "info", skip(db))]
    pub async fn get_recent(db: &DatabaseConnection, limit: u64) -> Result<Vec<content::Model>, DbErr> {
        info!(limit = limit, "Fetching recent content");

        let content_list = Content::find()
            .order_by_desc(content::Column::CreatedAt)
            .limit(limit)
            .all(db)
            .await?;

        info!(limit = limit, count = content_list.len(), "Retrieved recent content");
        Ok(content_list)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    #[ignore] // Requires database connection
    async fn test_get_all_content() {
        // Example test structure
        // let db = get_test_database_connection().await.unwrap();
        // let content = ContentService::get_all(&db).await.unwrap();
        // assert!(content.len() >= 0);
    }
}
