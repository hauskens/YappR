use serde::{Deserialize, Serialize};

#[cfg(feature = "database")]
use crate::external::api_client::PlatformVideo;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum JobQueues {
    General,
    Transcription,
    Video,
}

impl std::fmt::Display for JobQueues {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::General => write!(f, "general"),
            Self::Transcription => write!(f, "transcription"),
            Self::Video => write!(f, "video"),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum JobState {
    Pending,
    InProgress(u8),
    Completed,
    Failed,
}

impl std::fmt::Display for JobState {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Pending => write!(f, "pending"),
            Self::InProgress(progress) => write!(f, "in_progress ({}/100%)", progress),
            Self::Completed => write!(f, "completed"),
            Self::Failed => write!(f, "job failed"),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JobProgress {
    pub job_id: String,
    pub worker_id: String,
    pub progress: JobState,
    pub message: String,
}

/// Errors that can occur when working with NATS jobs
#[derive(Debug)]
pub enum JobError {
    /// Failed to serialize the job request
    SerializationError(rmp_serde::encode::Error),
    /// Failed to deserialize the job response
    DeserializationError(rmp_serde::decode::Error),
    /// NATS request error
    RequestError(async_nats::RequestError),
    /// NATS connection error
    ConnectError(async_nats::ConnectError),
    /// NATS subscribe error
    SubscribeError(async_nats::SubscribeError),
    /// Generic error for job execution failures
    ExecutionError(String),
}

impl std::fmt::Display for JobError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::SerializationError(e) => write!(f, "Serialization error: {}", e),
            Self::DeserializationError(e) => write!(f, "Deserialization error: {}", e),
            Self::RequestError(e) => write!(f, "NATS request error: {}", e),
            Self::ConnectError(e) => write!(f, "NATS connection error: {}", e),
            Self::SubscribeError(e) => write!(f, "NATS subscribe error: {}", e),
            Self::ExecutionError(e) => write!(f, "Job execution error: {}", e),
        }
    }
}

impl std::error::Error for JobError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::SerializationError(e) => Some(e),
            Self::DeserializationError(e) => Some(e),
            Self::RequestError(e) => Some(e),
            Self::ConnectError(e) => Some(e),
            Self::SubscribeError(e) => Some(e),
            Self::ExecutionError(_) => None,
        }
    }
}

impl From<rmp_serde::encode::Error> for JobError {
    fn from(e: rmp_serde::encode::Error) -> Self {
        Self::SerializationError(e)
    }
}

impl From<rmp_serde::decode::Error> for JobError {
    fn from(e: rmp_serde::decode::Error) -> Self {
        Self::DeserializationError(e)
    }
}

impl From<async_nats::RequestError> for JobError {
    fn from(e: async_nats::RequestError) -> Self {
        Self::RequestError(e)
    }
}

impl From<async_nats::ConnectError> for JobError {
    fn from(e: async_nats::ConnectError) -> Self {
        Self::ConnectError(e)
    }
}

impl From<async_nats::SubscribeError> for JobError {
    fn from(e: async_nats::SubscribeError) -> Self {
        Self::SubscribeError(e)
    }
}

pub trait Job: Serialize + Sized {
    const QUEUE: JobQueues;

    /// The response type for this job
    type Response: for<'de> Deserialize<'de>;

    /// Get the full NATS subject for this job type
    fn subject() -> String {
        format!("worker.queue.{}", Self::QUEUE)
    }

    /// Serialize this job to MessagePack bytes
    fn to_bytes(&self) -> Result<Vec<u8>, rmp_serde::encode::Error> {
        rmp_serde::to_vec(self)
    }

    /// Deserialize the response from MessagePack bytes
    fn response_from_bytes(bytes: &[u8]) -> Result<Self::Response, rmp_serde::decode::Error> {
        rmp_serde::from_slice(bytes)
    }
}

#[async_trait::async_trait]
pub trait NatsClientExt {
    /// Send a type-safe job request and await its response
    async fn request_job<J>(&self, job: J) -> Result<J::Response, JobError>
    where
        J: Job + Send,
        J::Response: Send;
}

#[async_trait::async_trait]
impl NatsClientExt for async_nats::Client {
    async fn request_job<J>(&self, job: J) -> Result<J::Response, JobError>
    where
        J: Job + Send,
        J::Response: Send,
    {
        let payload = job.to_bytes()?;
        let reply = self.request(J::subject(), payload.into()).await?;
        let response = J::response_from_bytes(&reply.payload)?;
        Ok(response)
    }
}

/// Request payload for a demo/test job
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DemoJobRequest {
    /// Unique job identifier
    pub job_id: String,
}

impl Job for DemoJobRequest {
    const QUEUE: JobQueues = JobQueues::General;
    type Response = DemoJobResponse;
}

/// Response payload from a demo/test job
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DemoJobResponse {
    /// Job identifier
    pub job_id: String,
    /// Unix timestamp when job completed
    pub completed_at: i64,
}

/// Request payload for fetching recent videos for a channel
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FetchVideosJob {
    /// Unique job identifier
    pub job_id: String,
    /// Channel ID to fetch videos for
    pub channel_id: i32,
    /// Maximum number of videos to fetch
    pub limit: u32,
}

impl Job for FetchVideosJob {
    const QUEUE: JobQueues = JobQueues::Video;
    type Response = FetchVideosResponse;
}

/// Response payload from a fetch videos job
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FetchVideosResponse {
    /// Job identifier
    pub job_id: String,
    /// Videos fetched from the platform API
    #[cfg(feature = "database")]
    pub videos: Vec<PlatformVideo>,
    /// Number of videos successfully fetched
    pub fetched_count: u32,
}

/// Request payload for updating/validating existing videos
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpdateVideosJob {
    /// Unique job identifier
    pub job_id: String,
    /// Database video IDs to update
    pub video_ids: Vec<i32>,
    /// Platform name (twitch, youtube)
    pub platform: String,
}

impl Job for UpdateVideosJob {
    const QUEUE: JobQueues = JobQueues::Video;
    type Response = UpdateVideosResponse;
}

/// Response payload from an update videos job
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpdateVideosResponse {
    /// Job identifier
    pub job_id: String,
    /// Videos that were found and updated
    #[cfg(feature = "database")]
    pub updated_videos: Vec<PlatformVideo>,
    /// Database video IDs that were not found on platform (should be deactivated)
    pub missing_video_ids: Vec<i32>,
    /// Number of videos successfully updated
    pub updated_count: u32,
    /// Number of videos not found
    pub missing_count: u32,
}
