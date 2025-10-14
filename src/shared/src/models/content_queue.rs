use crate::entities::{content, content_queue, content_queue_submissions, prelude::*};
use async_trait::async_trait;
use sea_orm::{
    ActiveModelTrait, ColumnTrait, DatabaseConnection, DbErr, EntityTrait, QueryFilter, Set,
};
use tracing::{info, instrument};

/// Extension trait for content_queue::Model providing convenient methods
#[async_trait]
pub trait ContentQueueExt {
    /// Get all submissions for this queue entry
    async fn get_submissions(
        &self,
        db: &DatabaseConnection,
    ) -> Result<Vec<content_queue_submissions::Model>, DbErr>;

    /// Get the content record for this queue entry
    async fn get_content(&self, db: &DatabaseConnection) -> Result<Option<content::Model>, DbErr>;

    /// Mark as watched
    async fn mark_watched(&self, db: &DatabaseConnection) -> Result<content_queue::Model, DbErr>;

    /// Mark as skipped
    async fn mark_skipped(&self, db: &DatabaseConnection) -> Result<content_queue::Model, DbErr>;

    /// Update score
    async fn update_score(
        &self,
        db: &DatabaseConnection,
        new_score: f64,
    ) -> Result<content_queue::Model, DbErr>;

    /// Disable this queue entry
    async fn disable(&self, db: &DatabaseConnection) -> Result<content_queue::Model, DbErr>;
}

#[async_trait]
impl ContentQueueExt for content_queue::Model {
    #[instrument(level = "info", skip(db))]
    async fn get_submissions(
        &self,
        db: &DatabaseConnection,
    ) -> Result<Vec<content_queue_submissions::Model>, DbErr> {
        let submissions = ContentQueueSubmissions::find()
            .filter(content_queue_submissions::Column::ContentQueueId.eq(self.id))
            .all(db)
            .await?;

        info!(
            queue_id = self.id,
            submission_count = submissions.len(),
            "Retrieved queue submissions"
        );
        Ok(submissions)
    }

    #[instrument(level = "info", skip(db))]
    async fn get_content(&self, db: &DatabaseConnection) -> Result<Option<content::Model>, DbErr> {
        let content = Content::find_by_id(self.content_id).one(db).await?;

        match &content {
            Some(c) => info!(queue_id = self.id, content_id = c.id, "Retrieved content"),
            None => info!(
                queue_id = self.id,
                content_id = self.content_id,
                "Content not found"
            ),
        }

        Ok(content)
    }

    #[instrument(level = "info", skip(db))]
    async fn mark_watched(&self, db: &DatabaseConnection) -> Result<content_queue::Model, DbErr> {
        info!(queue_id = self.id, "Marking as watched");

        let mut active: content_queue::ActiveModel = self.clone().into();
        active.watched = Set(true);
        active.update(db).await
    }

    #[instrument(level = "info", skip(db))]
    async fn mark_skipped(&self, db: &DatabaseConnection) -> Result<content_queue::Model, DbErr> {
        info!(queue_id = self.id, "Marking as skipped");

        let mut active: content_queue::ActiveModel = self.clone().into();
        active.skipped = Set(true);
        active.update(db).await
    }

    #[instrument(level = "info", skip(db))]
    async fn update_score(
        &self,
        db: &DatabaseConnection,
        new_score: f64,
    ) -> Result<content_queue::Model, DbErr> {
        info!(
            queue_id = self.id,
            old_score = self.score,
            new_score = new_score,
            "Updating score"
        );

        let mut active: content_queue::ActiveModel = self.clone().into();
        active.score = Set(new_score);
        active.update(db).await
    }

    #[instrument(level = "info", skip(db))]
    async fn disable(&self, db: &DatabaseConnection) -> Result<content_queue::Model, DbErr> {
        info!(queue_id = self.id, "Disabling queue entry");

        let mut active: content_queue::ActiveModel = self.clone().into();
        active.disabled = Set(true);
        active.update(db).await
    }
}
