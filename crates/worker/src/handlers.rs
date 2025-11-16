use async_nats::Client;
use tracing::{info, instrument};
use yappr_shared::jobs::{DemoJobRequest, DemoJobResponse, JobError, JobProgress, JobState};

/// Handle a demo/test job with progress updates
#[instrument(skip(client))]
pub async fn handle_demo_job(
    client: &Client,
    request: DemoJobRequest,
) -> Result<DemoJobResponse, JobError> {
    info!(
        job_id = %request.job_id,
        "Starting demo job"
    );

    let progress_subject = format!("worker.progress.{}", request.job_id);
    let worker_id = "worker-1"; // TODO: Get from config or generate unique ID

    // Simulate job with progress updates
    let iterations = 10;
    let sleep_ms = 500;

    for i in 1..=iterations {
        // Simulate work
        tokio::time::sleep(tokio::time::Duration::from_millis(sleep_ms)).await;

        // Calculate progress percentage
        let progress_pct = ((i as f32 / iterations as f32) * 100.0) as u8;

        // Publish progress update
        let progress = JobProgress {
            job_id: request.job_id.clone(),
            worker_id: worker_id.to_string(),
            progress: JobState::InProgress(progress_pct),
            message: format!("Completed iteration {}/{}", i, iterations),
        };

        let progress_bytes = rmp_serde::to_vec(&progress)?;
        client
            .publish(progress_subject.clone(), progress_bytes.into())
            .await
            .map_err(|e| JobError::RequestError(e.into()))?;

        info!(
            job_id = %request.job_id,
            iteration = i,
            total = iterations,
            progress_pct = progress_pct,
            "Progress update published"
        );
    }

    // Send final completion progress
    let final_progress = JobProgress {
        job_id: request.job_id.clone(),
        worker_id: worker_id.to_string(),
        progress: JobState::Completed,
        message: "Job completed successfully".to_string(),
    };

    let progress_bytes = rmp_serde::to_vec(&final_progress)?;
    client
        .publish(progress_subject, progress_bytes.into())
        .await
        .map_err(|e| JobError::RequestError(e.into()))?;

    // Create final response
    let response = DemoJobResponse {
        job_id: request.job_id.clone(),
        completed_at: chrono::Utc::now().timestamp(),
    };

    info!(
        job_id = %request.job_id,
        "Demo job completed"
    );

    Ok(response)
}
