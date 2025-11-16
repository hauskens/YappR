use serde::{Deserialize, Serialize};

/// Errors that can occur when working with NATS jobs
#[derive(Debug)]
pub enum JobError {
    /// Failed to serialize the job request
    SerializationError(rmp_serde::encode::Error),
    /// Failed to deserialize the job response
    DeserializationError(rmp_serde::decode::Error),
    /// NATS request error
    #[cfg(feature = "job-queue")]
    RequestError(async_nats::RequestError),
}

impl std::fmt::Display for JobError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            JobError::SerializationError(e) => write!(f, "Serialization error: {}", e),
            JobError::DeserializationError(e) => write!(f, "Deserialization error: {}", e),
            #[cfg(feature = "job-queue")]
            JobError::RequestError(e) => write!(f, "NATS request error: {}", e),
        }
    }
}

impl std::error::Error for JobError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            JobError::SerializationError(e) => Some(e),
            JobError::DeserializationError(e) => Some(e),
            #[cfg(feature = "job-queue")]
            JobError::RequestError(e) => Some(e),
        }
    }
}

impl From<rmp_serde::encode::Error> for JobError {
    fn from(e: rmp_serde::encode::Error) -> Self {
        JobError::SerializationError(e)
    }
}

impl From<rmp_serde::decode::Error> for JobError {
    fn from(e: rmp_serde::decode::Error) -> Self {
        JobError::DeserializationError(e)
    }
}

#[cfg(feature = "job-queue")]
impl From<async_nats::RequestError> for JobError {
    fn from(e: async_nats::RequestError) -> Self {
        JobError::RequestError(e)
    }
}

/// Core trait for type-safe NATS jobs
///
/// Implement this trait to define a job that can be sent over NATS.
/// The trait encodes the subject name and response type directly in the type system.
///
/// # Example
/// ```rust
/// use yappr_shared::jobs::{Job, HelloRequest, HelloResponse};
///
/// let request = HelloRequest { name: "World".to_string() };
/// assert_eq!(HelloRequest::SUBJECT, "worker.hello");
/// ```
pub trait Job: Serialize + Sized {
    /// The NATS subject this job should be published to
    const SUBJECT: &'static str;

    /// The response type for this job
    type Response: for<'de> Deserialize<'de>;

    /// Serialize this job to MessagePack bytes
    fn to_bytes(&self) -> Result<Vec<u8>, rmp_serde::encode::Error> {
        rmp_serde::to_vec(self)
    }

    /// Deserialize the response from MessagePack bytes
    fn response_from_bytes(bytes: &[u8]) -> Result<Self::Response, rmp_serde::decode::Error> {
        rmp_serde::from_slice(bytes)
    }
}

/// Extension trait for async-nats Client to support type-safe job requests
///
/// # Example
/// ```rust,no_run
/// use yappr_shared::jobs::{NatsClientExt, HelloRequest};
///
/// # async fn example() -> Result<(), Box<dyn std::error::Error>> {
/// let client = async_nats::connect("nats://localhost:4222").await?;
/// let request = HelloRequest { name: "World".to_string() };
/// let response = client.request_job(request).await?;
/// println!("{}", response.message);
/// # Ok(())
/// # }
/// ```
#[cfg(feature = "job-queue")]
#[async_trait::async_trait]
pub trait NatsClientExt {
    /// Send a type-safe job request and await its response
    async fn request_job<J>(&self, job: J) -> Result<J::Response, JobError>
    where
        J: Job + Send,
        J::Response: Send;
}

#[cfg(feature = "job-queue")]
#[async_trait::async_trait]
impl NatsClientExt for async_nats::Client {
    async fn request_job<J>(&self, job: J) -> Result<J::Response, JobError>
    where
        J: Job + Send,
        J::Response: Send,
    {
        let payload = job.to_bytes()?;
        let reply = self.request(J::SUBJECT.to_string(), payload.into()).await?;
        let response = J::response_from_bytes(&reply.payload)?;
        Ok(response)
    }
}

/// Request payload for the hello worker
///
/// Other services can import this type to construct requests:
/// ```rust
/// use yappr_shared::jobs::{Job, NatsClientExt, HelloRequest};
///
/// # async fn example() -> Result<(), Box<dyn std::error::Error>> {
/// let client = async_nats::connect("nats://localhost:4222").await?;
/// let request = HelloRequest { name: "World".to_string() };
/// let response = client.request_job(request).await?;
/// # Ok(())
/// # }
/// ```
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HelloRequest {
    pub name: String,
}

impl Job for HelloRequest {
    const SUBJECT: &'static str = "worker.hello";
    type Response = HelloResponse;
}

/// Response payload from the hello worker
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HelloResponse {
    pub message: String,
    pub timestamp: i64,
}
