use sea_orm::{
    ActiveModelTrait, ColumnTrait, DatabaseConnection, EntityTrait, PaginatorTrait, QueryFilter,
};
use tracing::{info, instrument};
use yappr_shared::entities::{content_queue_submissions, prelude::*};
use yappr_shared::models::content_queue::ContentQueueExt;

/// Discord message deletion event
/// Unlike platform moderation events (bans/timeouts), this handles single message deletions
pub struct DiscordMessageDeletion {
    pub message_id: u64,
    pub channel_id: u64,
}

impl DiscordMessageDeletion {
    pub fn new(message_id: u64, channel_id: u64) -> Self {
        Self {
            message_id,
            channel_id,
        }
    }

    /// Handle message deletion - remove corresponding content queue submission
    #[instrument(level = "info", skip(db))]
    pub async fn handle(db: &DatabaseConnection, message_id: u64) -> Result<(), eyre::Report> {
        let message_id_i64 = message_id as i64;

        // Find submission with this message ID
        let submission = ContentQueueSubmissions::find()
            .filter(content_queue_submissions::Column::SubmissionSourceId.eq(message_id_i64))
            .filter(content_queue_submissions::Column::SubmissionSourceType.eq("Discord"))
            .one(db)
            .await?;

        if let Some(submission) = submission {
            info!(
                submission_id = submission.id,
                content_queue_id = submission.content_queue_id,
                "Found submission for deleted message"
            );

            let content_queue_id = submission.content_queue_id;

            // Delete the submission
            let active: content_queue_submissions::ActiveModel = submission.into();
            active.delete(db).await?;

            info!(submission_id = content_queue_id, "Deleted submission");

            // Check if the content queue entry is now empty
            let remaining_submissions = ContentQueueSubmissions::find()
                .filter(content_queue_submissions::Column::ContentQueueId.eq(content_queue_id))
                .count(db)
                .await?;

            if remaining_submissions == 0 {
                // Disable the content queue entry
                if let Some(queue_entry) =
                    ContentQueue::find_by_id(content_queue_id).one(db).await?
                {
                    info!(
                        content_queue_id = content_queue_id,
                        "Disabling empty content queue entry"
                    );
                    queue_entry.disable(db).await?;
                }
            }
        } else {
            info!(
                message_id = message_id,
                "No submission found for deleted message"
            );
        }

        Ok(())
    }
}
