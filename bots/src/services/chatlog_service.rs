use sea_orm::{ActiveModelTrait, DatabaseConnection, DbErr, Set};
use std::sync::Arc;
use tokio::sync::Mutex;
use tokio::time::{Duration, interval};
use tracing::{error, info, instrument};
use yappr_shared::entities::chatlogs;

/// Batched chatlog service for efficient database writes
pub struct ChatlogService {
    db: DatabaseConnection,
    buffer: Arc<Mutex<Vec<chatlogs::ActiveModel>>>,
    max_buffer_size: usize,
    commit_interval: Duration,
}

impl ChatlogService {
    pub fn new(db: DatabaseConnection) -> Self {
        Self {
            db,
            buffer: Arc::new(Mutex::new(Vec::new())),
            max_buffer_size: 100,
            commit_interval: Duration::from_secs(5),
        }
    }

    /// Add a chat message to the buffer
    #[instrument(level = "debug", skip(self))]
    pub async fn add_message(
        &self,
        channel_id: i32,
        timestamp: chrono::NaiveDateTime,
        username: String,
        message: String,
        external_user_account_id: Option<i32>,
    ) -> Result<(), DbErr> {
        let chat_log = chatlogs::ActiveModel {
            channel_id: Set(channel_id),
            timestamp: Set(timestamp),
            username: Set(username),
            message: Set(message),
            external_user_account_id: Set(external_user_account_id),
            ..Default::default()
        };

        let mut buffer = self.buffer.lock().await;
        buffer.push(chat_log);

        // Check if we should commit based on buffer size
        if buffer.len() >= self.max_buffer_size {
            drop(buffer); // Release lock before commit
            self.commit().await?;
        }

        Ok(())
    }

    /// Commit all buffered messages to the database
    #[instrument(level = "info", skip(self))]
    pub async fn commit(&self) -> Result<usize, DbErr> {
        let mut buffer = self.buffer.lock().await;

        if buffer.is_empty() {
            return Ok(0);
        }

        let count = buffer.len();
        let messages = buffer.drain(..).collect::<Vec<_>>();
        drop(buffer); // Release lock before DB operation

        // Batch insert all messages
        for msg in messages {
            msg.insert(&self.db).await?;
        }

        info!(count = count, "Committed chat messages to database");
        Ok(count)
    }

    /// Start periodic commit task
    pub async fn start_periodic_commit(self: Arc<Self>) {
        let mut commit_timer = interval(self.commit_interval);

        loop {
            commit_timer.tick().await;

            if let Err(e) = self.commit().await {
                error!(error = %e, "Failed to commit chat messages");
            }
        }
    }

    /// Flush any remaining messages (call on shutdown)
    pub async fn flush(&self) -> Result<usize, DbErr> {
        self.commit().await
    }
}
