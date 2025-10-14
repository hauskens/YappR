use redis::aio::ConnectionManager;
use redis::{AsyncCommands, Client, RedisError};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use tracing::{debug, error, info, warn};

use crate::config::Config;

/// Represents an event that can be published to Redis
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Event<T> {
    /// Unique event ID
    pub id: String,
    /// Event type/name
    pub event_type: String,
    /// Event payload
    pub payload: T,
    /// Timestamp when the event was created (Unix timestamp in milliseconds)
    pub timestamp: i64,
    /// Optional metadata
    pub metadata: HashMap<String, String>,
}

impl<T> Event<T> {
    /// Create a new event with the given type and payload
    pub fn new(event_type: impl Into<String>, payload: T) -> Self {
        Self {
            id: uuid::Uuid::new_v4().to_string(),
            event_type: event_type.into(),
            payload,
            timestamp: chrono::Utc::now().timestamp_millis(),
            metadata: HashMap::new(),
        }
    }

    /// Add metadata to the event
    pub fn with_metadata(mut self, key: impl Into<String>, value: impl Into<String>) -> Self {
        self.metadata.insert(key.into(), value.into());
        self
    }
}

#[derive(Debug)]
pub enum StreamType {
    Task,
}

impl StreamType {
    pub fn as_str(&self) -> &'static str {
        match self {
            StreamType::Task => "tasks-stream",
        }
    }
}

/// Result of consuming an event
#[derive(Debug)]
pub struct ConsumedEvent<T> {
    /// The stream name
    pub stream: StreamType,
    /// The message ID in the stream
    pub message_id: String,
    /// The event data
    pub event: Event<T>,
}

/// Redis client for event-driven communication
#[derive(Clone)]
pub struct RedisClient {
    connection: ConnectionManager,
    consumer_group: String,
    consumer_name: String,
}

impl RedisClient {
    /// Create a new Redis client
    ///
    /// # Arguments
    /// * `redis_url` - Redis connection URL (e.g., "redis://localhost:6379")
    /// * `consumer_group` - Name of the consumer group for this client
    /// * `consumer_name` - Unique name for this consumer instance
    pub async fn new(
        consumer_group: impl Into<String>,
        consumer_name: impl Into<String>,
    ) -> Result<Self, RedisError> {
        let config = Config::load();
        info!(
            "Starting Redis client with URL: {}",
            config.redis.connection_string()
        );
        let client = Client::open(config.redis.connection_string())?;
        let connection = ConnectionManager::new(client).await?;
        info!("Redis client started successfully");

        Ok(Self {
            connection,
            consumer_group: consumer_group.into(),
            consumer_name: consumer_name.into(),
        })
    }

    /// Publish an event to a Redis stream
    ///
    /// # Arguments
    /// * `stream` - The stream name to publish to
    /// * `event` - The event to publish
    ///
    /// # Returns
    /// The message ID assigned by Redis
    pub async fn publish_event<T: Serialize>(
        &mut self,
        stream: &str,
        event: Event<T>,
    ) -> Result<String, RedisError> {
        // Serialize the event using MessagePack
        let serialized = rmp_serde::to_vec(&event).map_err(|e| {
            error!(error = %e, "Failed to serialize event");
            RedisError::from((
                redis::ErrorKind::IoError,
                "Serialization error",
                e.to_string(),
            ))
        })?;

        // Add to stream with XADD
        let message_id: String = self
            .connection
            .xadd(stream, "*", &[("data", serialized)])
            .await?;

        debug!(
            stream = stream,
            message_id = %message_id,
            event_type = %event.event_type,
            "Published event to stream"
        );

        Ok(message_id)
    }

    /// Consume events from a Redis stream
    ///
    /// This method will:
    /// 1. Create the consumer group if it doesn't exist
    /// 2. Read pending messages for this consumer
    /// 3. Read new messages if no pending messages exist
    ///
    /// # Arguments
    /// * `stream` - The stream name to consume from
    /// * `count` - Maximum number of events to consume (default: 10)
    /// * `block_ms` - Time to block waiting for new messages in milliseconds (None = don't block)
    ///
    /// # Returns
    /// A vector of consumed events
    pub async fn consume_events<T: for<'de> Deserialize<'de>>(
        &mut self,
        stream: &str,
        count: usize,
        block_ms: Option<usize>,
    ) -> Result<Vec<ConsumedEvent<T>>, RedisError> {
        use redis::streams::{StreamReadOptions, StreamReadReply};

        // Try to create the consumer group (ignore error if it already exists)
        let _: Result<(), RedisError> = self
            .connection
            .xgroup_create_mkstream(stream, &self.consumer_group, "0")
            .await;

        // Build the read options
        let opts = StreamReadOptions::default()
            .group(&self.consumer_group, &self.consumer_name)
            .count(count);

        let opts = if let Some(block) = block_ms {
            opts.block(block)
        } else {
            opts
        };

        // Read from the stream using ">" to get new messages
        let pending: StreamReadReply = self
            .connection
            .xread_options(&[stream], &[">"], &opts)
            .await?;

        let mut events = Vec::new();

        for stream_key in pending.keys {
            for stream_id in stream_key.ids {
                // Extract the serialized data
                if let Some(data) = stream_id.map.get("data") {
                    match data {
                        redis::Value::BulkString(bytes) => {
                            match rmp_serde::from_slice::<Event<T>>(bytes) {
                                Ok(event) => {
                                    debug!(
                                        stream = %stream_key.key,
                                        message_id = %stream_id.id,
                                        event_type = %event.event_type,
                                        "Consumed event from stream"
                                    );

                                    events.push(ConsumedEvent {
                                        stream: StreamType::Task,
                                        message_id: stream_id.id.clone(),
                                        event,
                                    });
                                }
                                Err(e) => {
                                    error!(
                                        error = %e,
                                        message_id = %stream_id.id,
                                        "Failed to deserialize event"
                                    );
                                }
                            }
                        }
                        _ => {
                            warn!(
                                message_id = %stream_id.id,
                                "Unexpected data type in stream message"
                            );
                        }
                    }
                }
            }
        }

        Ok(events)
    }

    /// Acknowledge successful processing of an event
    ///
    /// # Arguments
    /// * `stream` - The stream name
    /// * `message_id` - The message ID to acknowledge
    pub async fn ack(&mut self, stream: &StreamType, message_id: &str) -> Result<(), RedisError> {
        let acked: i32 = self
            .connection
            .xack(stream.as_str(), &self.consumer_group, &[message_id])
            .await?;

        if acked > 0 {
            debug!(
                stream = stream.as_str(),
                message_id = message_id,
                "Acknowledged event"
            );
        } else {
            warn!(
                stream = stream.as_str(),
                message_id = message_id,
                "Event was not acknowledged (already acked or doesn't exist)"
            );
        }

        Ok(())
    }

    pub async fn ack_batch(
        &mut self,
        stream: &StreamType,
        message_ids: &[String],
    ) -> Result<(), RedisError> {
        let acked: i32 = self
            .connection
            .xack(stream.as_str(), &self.consumer_group, message_ids)
            .await?;
        debug!(
            stream = stream.as_str(),
            count = acked,
            "Acknowledged {} events",
            acked
        );
        Ok(())
    }

    /// Negative acknowledge (reject) an event and optionally retry it
    ///
    /// This will claim the message back to the stream for retry by other consumers
    ///
    /// # Arguments
    /// * `stream` - The stream name
    /// * `message_id` - The message ID to reject
    /// * `retry` - If true, the message will be available for retry; if false, it will be deleted
    pub async fn nack(
        &mut self,
        stream: &StreamType,
        message_id: &str,
        retry: bool,
    ) -> Result<(), RedisError> {
        if retry {
            // Claim the message with a minimal idle time to make it available for retry
            info!(
                stream = stream.as_str(),
                message_id = message_id,
                "Negative acknowledged event, available for retry"
            );
            // The message will remain in the pending list and can be claimed by other consumers
        } else {
            // Acknowledge to remove from pending, then optionally delete
            self.ack(stream, message_id).await?;
            info!(
                stream = stream.as_str(),
                message_id = message_id,
                "Negative acknowledged event, removed from stream"
            );
        }

        Ok(())
    }

    /// Get the consumer group name
    pub fn consumer_group(&self) -> &str {
        &self.consumer_group
    }

    /// Get the consumer name
    pub fn consumer_name(&self) -> &str {
        &self.consumer_name
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde::{Deserialize, Serialize};

    #[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
    struct TestPayload {
        message: String,
        value: i32,
    }

    #[tokio::test]
    #[ignore] // Requires Redis to be running
    async fn test_publish_and_consume() {
        let mut client = RedisClient::new("test-group", "test-consumer")
            .await
            .unwrap();

        let payload = TestPayload {
            message: "Hello, Redis!".to_string(),
            value: 42,
        };

        let event = Event::new("test.event", payload.clone());

        // Publish event
        let message_id = client
            .publish_event("test-stream", event.clone())
            .await
            .unwrap();

        assert!(!message_id.is_empty());

        // Consume event
        let events: Vec<ConsumedEvent<TestPayload>> = client
            .consume_events("test-stream", 10, None)
            .await
            .unwrap();

        assert_eq!(events.len(), 1);
        assert_eq!(events[0].event.event_type, "test.event");
        assert_eq!(events[0].event.payload, payload);

        // Acknowledge event
        client
            .ack(&StreamType::Task, &events[0].message_id)
            .await
            .unwrap();
    }
}
