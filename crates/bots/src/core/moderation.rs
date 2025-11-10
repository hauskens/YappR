use sea_orm::{
    ActiveModelTrait, ColumnTrait, DatabaseConnection, EntityTrait, PaginatorTrait, QueryFilter,
    Set,
};
use tracing::{info, instrument};
use yappr_shared::entities::{
    content_queue, content_queue_submissions, moderation_actions, prelude::*,
};
use yappr_shared::models::content_queue::ContentQueueExt;
use yappr_shared::models::platforms::AccountPlatform;
use yappr_shared::user::UserService;

/// Platform-agnostic moderation event trait
/// Each bot platform implements this trait to provide a unified interface
pub trait PlatformModerationEvent {
    /// User ID of the person being moderated
    fn target_user_id(&self) -> &str;

    /// Username of the person being moderated
    fn target_username(&self) -> &str;

    /// Broadcaster/channel ID where moderation occurred
    fn broadcaster_id(&self) -> &str;

    /// Whether this is a permanent ban
    fn is_ban(&self) -> bool;

    /// Duration of timeout (None for permanent bans)
    fn duration(&self) -> Option<chrono::Duration>;

    /// Reason for the moderation action (if available)
    fn reason(&self) -> Option<&str>;

    /// The platform this event came from
    fn platform(&self) -> AccountPlatform;
}

/// Generic moderation handler that works with any platform implementing PlatformModerationEvent
pub struct ModerationHandler {
    db: DatabaseConnection,
}

impl ModerationHandler {
    pub fn new(db: DatabaseConnection) -> Self {
        Self { db }
    }

    /// Handle moderation event from any platform
    #[instrument(level = "info", skip(self, event), fields(
        target_user_id = %event.target_user_id(),
        broadcaster_id = %event.broadcaster_id(),
    ))]
    pub async fn handle_moderation_event<E: PlatformModerationEvent>(
        &self,
        event: &E,
        channel_id: i32,
        broadcaster_id: i32,
    ) -> Result<(), eyre::Report> {
        let action_type = if event.is_ban() { "ban" } else { "timeout" };

        let duration_seconds: Option<i32> = event.duration().map(|d| d.num_seconds() as i32);
        let expires_at: Option<chrono::NaiveDateTime> = duration_seconds.map(|seconds| {
            chrono::Utc::now().naive_utc() + chrono::Duration::seconds(seconds as i64)
        });

        info!(
            action_type = ?action_type,
            duration_seconds = ?duration_seconds,
            "Processing moderation event"
        );

        // Get or create user
        let user = self.get_or_create_user(event).await?;

        // Create moderation action record
        let reason = event
            .reason()
            .map(|r| r.to_string())
            .unwrap_or_else(|| format!("{:?} moderator action", event.platform()));

        let moderation_action = moderation_actions::ActiveModel {
            target_user_id: Set(user.id),
            action_type: Set(action_type.to_string()),
            scope: Set("channel".to_string()),
            channel_id: Set(Some(channel_id)),
            reason: Set(reason),
            duration_seconds: Set(duration_seconds),
            expires_at: Set(expires_at),
            issued_by: Set(None),
            issued_at: Set(chrono::Utc::now().naive_utc()),
            active: Set(true),
            ..Default::default()
        };

        moderation_action.insert(&self.db).await?;

        // Clean up content queue entries
        self.cleanup_content_queue(user.id, broadcaster_id, action_type, duration_seconds)
            .await?;

        Ok(())
    }

    /// Get or create user from moderation event
    /// Delegates to shared UserService
    async fn get_or_create_user<E: PlatformModerationEvent>(
        &self,
        event: &E,
    ) -> Result<yappr_shared::entities::users::Model, eyre::Report> {
        Ok(UserService::get_or_create_user(
            &self.db,
            event.target_user_id(),
            event.target_username(),
            event.platform(),
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
                self.cleanup_timeout(user_id, broadcaster_id, duration)
                    .await?;
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
