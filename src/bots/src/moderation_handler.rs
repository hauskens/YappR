use sea_orm::{ActiveModelTrait, ColumnTrait, DatabaseConnection, EntityTrait, QueryFilter, Set, PaginatorTrait};
use tracing::{info, instrument};
use twitch_api::eventsub::channel::chat::ChannelChatClearUserMessagesV1Payload;
use yappr_shared::entities::{
    content_queue, content_queue_submissions, moderation_actions, prelude::*,
};
use yappr_shared::entities::sea_orm_active_enums::Accountsource;
use yappr_shared::models::content_queue::ContentQueueExt;
use yappr_shared::services::user::UserService;

pub struct ModerationHandler {
    db: DatabaseConnection,
}

impl ModerationHandler {
    pub fn new(db: DatabaseConnection) -> Self {
        Self { db }
    }

    /// Handle user timeout/ban event
    #[instrument(level = "info", skip(self, event), fields(
        target_user_id = %event.target_user_id,
        broadcaster_user_id = %event.broadcaster_user_id,
    ))]
    pub async fn handle_moderation_event(
        &self,
        event: &ChannelChatClearUserMessagesV1Payload,
        channel_id: i32,
        broadcaster_id: i32,
    ) -> Result<(), eyre::Report> {
        // For ChannelChatClearUserMessagesV1, we don't have duration info
        // Treat all as bans for now - proper timeout handling would require
        // subscribing to the ban/timeout specific events
        let action_type = "ban".to_string();
        let duration_seconds: Option<i32> = None;
        let expires_at: Option<chrono::NaiveDateTime> = None;

        info!(
            action_type = ?action_type,
            duration_seconds = ?duration_seconds,
            "Processing moderation event"
        );

        // Get or create user
        let user = self
            .get_or_create_user(event.target_user_id.as_str(), event.target_user_name.as_str())
            .await?;

        // Create moderation action record
        let moderation_action = moderation_actions::ActiveModel {
            target_user_id: Set(user.id),
            action_type: Set(action_type.clone()),
            scope: Set("channel".to_string()),
            channel_id: Set(Some(channel_id)),
            reason: Set("Twitch moderator action".to_string()),
            duration_seconds: Set(duration_seconds),
            expires_at: Set(expires_at),
            issued_by: Set(None),
            issued_at: Set(chrono::Utc::now().naive_utc()),
            active: Set(true),
            ..Default::default()
        };

        moderation_action.insert(&self.db).await?;

        // Clean up content queue entries
        self.cleanup_content_queue(user.id, broadcaster_id, &action_type, duration_seconds)
            .await?;

        Ok(())
    }

    /// Get or create user by Twitch ID
    /// Delegates to shared UserService
    async fn get_or_create_user(
        &self,
        twitch_user_id: &str,
        username: &str,
    ) -> Result<yappr_shared::entities::users::Model, eyre::Report> {
        Ok(UserService::get_or_create_user(
            &self.db,
            twitch_user_id,
            username,
            Accountsource::Twitch,
            None, // No color in moderation events
            None, // No avatar URL in moderation events
        )
        .await?)
    }

    /// Clean up content queue entries for moderated users
    #[instrument(level = "info", skip(self))]
    async fn cleanup_content_queue(
        &self,
        user_id: i32,
        broadcaster_id: i32,
        action_type: &str,
        duration_seconds: Option<i32>,
    ) -> Result<(), eyre::Report> {
        match action_type {
            "ban" => {
                // For bans, remove all unwatched/unskipped submissions
                self.cleanup_ban(user_id, broadcaster_id).await?;
            }
            "timeout" => {
                // For timeouts, remove submissions from past X seconds (minimum 60s)
                let duration = duration_seconds.unwrap_or(60).max(60);
                self.cleanup_timeout(user_id, broadcaster_id, duration).await?;
            }
            _ => {}
        }

        Ok(())
    }

    /// Clean up submissions for banned user
    async fn cleanup_ban(&self, user_id: i32, broadcaster_id: i32) -> Result<usize, eyre::Report> {
        let submissions = ContentQueueSubmissions::find()
            .find_also_related(ContentQueue)
            .filter(content_queue_submissions::Column::UserId.eq(user_id))
            .filter(content_queue::Column::BroadcasterId.eq(broadcaster_id))
            .filter(content_queue::Column::Watched.eq(false))
            .filter(content_queue::Column::Skipped.eq(false))
            .all(&self.db)
            .await?;

        let count = submissions.len();

        for (submission, _) in submissions {
            let active: content_queue_submissions::ActiveModel = submission.into();
            active.delete(&self.db).await?;
        }

        info!(count = count, "Cleaned up submissions for banned user");

        // Disable empty queue entries
        self.disable_empty_queue_entries(broadcaster_id).await?;

        Ok(count)
    }

    /// Clean up submissions for timed out user
    async fn cleanup_timeout(
        &self,
        user_id: i32,
        broadcaster_id: i32,
        duration_seconds: i32,
    ) -> Result<usize, eyre::Report> {
        let cutoff_time =
            chrono::Utc::now().naive_utc() - chrono::Duration::seconds(duration_seconds as i64);

        let submissions = ContentQueueSubmissions::find()
            .find_also_related(ContentQueue)
            .filter(content_queue_submissions::Column::UserId.eq(user_id))
            .filter(content_queue::Column::BroadcasterId.eq(broadcaster_id))
            .filter(content_queue::Column::Watched.eq(false))
            .filter(content_queue::Column::Skipped.eq(false))
            .filter(content_queue_submissions::Column::SubmittedAt.gte(cutoff_time))
            .all(&self.db)
            .await?;

        let count = submissions.len();

        for (submission, _) in submissions {
            let active: content_queue_submissions::ActiveModel = submission.into();
            active.delete(&self.db).await?;
        }

        info!(
            count = count,
            duration_seconds = duration_seconds,
            "Cleaned up submissions for timed out user"
        );

        // Disable empty queue entries
        self.disable_empty_queue_entries(broadcaster_id).await?;

        Ok(count)
    }

    /// Disable queue entries that have no submissions
    async fn disable_empty_queue_entries(&self, broadcaster_id: i32) -> Result<(), eyre::Report> {
        let queue_entries = ContentQueue::find()
            .filter(content_queue::Column::BroadcasterId.eq(broadcaster_id))
            .filter(content_queue::Column::Watched.eq(false))
            .filter(content_queue::Column::Skipped.eq(false))
            .filter(content_queue::Column::Disabled.eq(false))
            .all(&self.db)
            .await?;

        for entry in queue_entries {
            // Check if it has any submissions
            let submission_count = ContentQueueSubmissions::find()
                .filter(content_queue_submissions::Column::ContentQueueId.eq(entry.id))
                .count(&self.db)
                .await?;

            if submission_count == 0 {
                // Disable using the ContentQueueExt trait
                entry.disable(&self.db).await?;
                info!(queue_id = entry.id, "Disabled empty queue entry");
            }
        }

        Ok(())
    }
}
