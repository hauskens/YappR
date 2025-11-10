use sea_orm::{ActiveModelTrait, ColumnTrait, DatabaseConnection, EntityTrait, QueryFilter, Set};
use serenity::all::{ChannelId, Context, MessageId};
use std::collections::{HashMap, HashSet};
use std::sync::Arc;
use tokio::sync::{RwLock, mpsc};
use tokio::time::{Duration, sleep};
use tracing::{error, info, instrument, warn};
use yappr_shared::entities::{content_queue_submissions, prelude::*};

/// Manages reaction tracking and vote counting for Discord messages
pub struct ReactionHandler {
    db: DatabaseConnection,
    /// Message IDs that are being tracked for reactions
    tracked_messages: Arc<RwLock<HashSet<u64>>>,
    /// Channel for debounced vote updates
    vote_update_tx: mpsc::UnboundedSender<u64>,
}

impl ReactionHandler {
    pub fn new(db: DatabaseConnection) -> Self {
        let tracked_messages = Arc::new(RwLock::new(HashSet::new()));
        let (vote_update_tx, vote_update_rx) = mpsc::unbounded_channel();

        // Spawn background task for debounced vote updates
        let db_clone = db.clone();
        let tracked_messages_clone = tracked_messages.clone();
        tokio::spawn(Self::vote_update_worker(
            db_clone,
            tracked_messages_clone,
            vote_update_rx,
        ));

        Self {
            db,
            tracked_messages,
            vote_update_tx,
        }
    }

    /// Add a message ID to the tracking set
    pub async fn track_message(&self, message_id: u64) {
        let mut tracked = self.tracked_messages.write().await;
        tracked.insert(message_id);
        info!(message_id = message_id, "Tracking message for reactions");
    }

    /// Remove a message ID from tracking (e.g., when deleted)
    pub async fn untrack_message(&self, message_id: u64) {
        let mut tracked = self.tracked_messages.write().await;
        tracked.remove(&message_id);
        info!(message_id = message_id, "Stopped tracking message");
    }

    /// Check if a message is being tracked
    pub async fn is_tracked(&self, message_id: u64) -> bool {
        let tracked = self.tracked_messages.read().await;
        tracked.contains(&message_id)
    }

    /// Schedule a debounced vote update for a message
    pub async fn schedule_vote_update(&self, message_id: u64) {
        if !self.is_tracked(message_id).await {
            return;
        }

        if let Err(e) = self.vote_update_tx.send(message_id) {
            error!(error = %e, "Failed to schedule vote update");
        }
    }

    /// Background worker that processes debounced vote updates
    async fn vote_update_worker(
        _db: DatabaseConnection,
        tracked_messages: Arc<RwLock<HashSet<u64>>>,
        mut vote_update_rx: mpsc::UnboundedReceiver<u64>,
    ) {
        // Map of message_id -> last update time
        let mut pending_updates: HashMap<u64, tokio::time::Instant> = HashMap::new();
        let debounce_duration = Duration::from_secs(5);

        loop {
            tokio::select! {
                // Receive new vote update requests
                Some(message_id) = vote_update_rx.recv() => {
                    pending_updates.insert(message_id, tokio::time::Instant::now() + debounce_duration);
                }

                // Check for pending updates that are ready
                _ = sleep(Duration::from_millis(100)) => {
                    let now = tokio::time::Instant::now();
                    let ready: Vec<u64> = pending_updates
                        .iter()
                        .filter(|&(_, time)| *time <= now)
                        .map(|(&id, _)| id)
                        .collect();

                    for message_id in ready {
                        pending_updates.remove(&message_id);

                        // Check if still tracked
                        let is_tracked = {
                            let tracked = tracked_messages.read().await;
                            tracked.contains(&message_id)
                        };

                        if is_tracked {
                            info!(message_id = message_id, "Processing debounced vote update");
                            // Note: We can't count votes here without Discord context
                            // The actual counting will happen when the bot processes the reaction
                            // This is just the debounce mechanism
                        }
                    }
                }
            }
        }
    }

    /// Count votes for a message and update submission weight
    #[instrument(level = "info", skip(self, ctx))]
    pub async fn count_and_update_votes(
        &self,
        ctx: &Context,
        channel_id: ChannelId,
        message_id: MessageId,
    ) -> Result<usize, eyre::Report> {
        // Fetch the message to get reactions
        let message = channel_id.message(&ctx.http, message_id).await?;

        // Count unique users who reacted (excluding bots and message author)
        let mut unique_users = HashSet::new();

        for reaction in &message.reactions {
            // Get all users who reacted with this emoji
            let users = channel_id
                .reaction_users(
                    &ctx.http,
                    message_id,
                    reaction.reaction_type.clone(),
                    None,
                    None,
                )
                .await?;

            for user in users {
                // Exclude bots and the message author
                if !user.bot && user.id != message.author.id {
                    unique_users.insert(user.id.get());
                }
            }
        }

        let vote_count = unique_users.len();
        info!(
            message_id = message_id.get(),
            vote_count = vote_count,
            "Counted votes for message"
        );

        // Update submission weight in database
        self.update_submission_weight(message_id.get(), vote_count)
            .await?;

        Ok(vote_count)
    }

    /// Update submission weight for a message
    async fn update_submission_weight(
        &self,
        message_id: u64,
        vote_count: usize,
    ) -> Result<(), eyre::Report> {
        let message_id_i64 = message_id as i64;

        // Find submission with this message ID
        let submission = ContentQueueSubmissions::find()
            .filter(content_queue_submissions::Column::SubmissionSourceId.eq(message_id_i64))
            .filter(content_queue_submissions::Column::SubmissionSourceType.eq("Discord"))
            .one(&self.db)
            .await?;

        if let Some(submission) = submission {
            // Update weight (base weight + vote count)
            let new_weight = 1.0 + vote_count as f64;

            let mut active: content_queue_submissions::ActiveModel = submission.into();
            active.weight = Set(new_weight);
            active.update(&self.db).await?;

            info!(
                message_id = message_id,
                new_weight = new_weight,
                "Updated submission weight"
            );
        } else {
            warn!(message_id = message_id, "No submission found for message");
        }

        Ok(())
    }

    /// Load tracked messages from database on startup
    pub async fn load_tracked_messages(&self, broadcaster_id: i32) -> Result<(), eyre::Report> {
        use yappr_shared::entities::content_queue;

        let submissions = ContentQueueSubmissions::find()
            .inner_join(ContentQueue)
            .filter(content_queue_submissions::Column::SubmissionSourceType.eq("Discord"))
            .filter(content_queue::Column::BroadcasterId.eq(broadcaster_id))
            .filter(content_queue::Column::Watched.eq(false))
            .filter(content_queue::Column::Skipped.eq(false))
            .all(&self.db)
            .await?;

        let mut tracked = self.tracked_messages.write().await;
        for submission in submissions {
            let message_id = submission.submission_source_id as u64;
            tracked.insert(message_id);
            info!(
                message_id = message_id,
                "Loaded tracked message from database"
            );
        }

        info!(
            count = tracked.len(),
            broadcaster_id = broadcaster_id,
            "Loaded tracked messages for broadcaster"
        );

        Ok(())
    }
}
