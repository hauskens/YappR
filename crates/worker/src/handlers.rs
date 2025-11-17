use async_nats::Client;
use std::collections::HashMap;
use tracing::{debug, error, info, instrument};
use yappr_shared::jobs::{
    DemoJobRequest, DemoJobResponse, FetchVideosJob, FetchVideosResponse, JobError, JobProgress,
    JobState, UpdateVideosJob, UpdateVideosResponse,
};

use yappr_shared::external::api_client::{ApiClient, PlatformApiClient};
use yappr_shared::external::twitch::TwitchApiClient;
use yappr_shared::external::youtube::YouTubeApiClient;
use yappr_shared::services::channel::ChannelService;
use yappr_shared::services::video::VideoService;

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

/// Handle a fetch videos job - fetches recent videos for a channel from platform API
#[instrument(skip(client))]
pub async fn handle_fetch_videos_job(
    client: &Client,
    request: FetchVideosJob,
) -> Result<FetchVideosResponse, JobError> {
    info!(
        job_id = %request.job_id,
        channel_id = request.channel_id,
        limit = request.limit,
        "Starting fetch videos job"
    );

    let progress_subject = format!("worker.progress.{}", request.job_id);
    let worker_id = "worker-1"; // TODO: Get from config or generate unique ID

    // Publish initial progress
    let progress = JobProgress {
        job_id: request.job_id.clone(),
        worker_id: worker_id.to_string(),
        progress: JobState::InProgress(10),
        message: "Connecting to database".to_string(),
    };
    let progress_bytes = rmp_serde::to_vec(&progress)?;
    client
        .publish(progress_subject.clone(), progress_bytes.into())
        .await
        .map_err(|e| JobError::RequestError(e.into()))?;

    // Load config and connect to database
    let db = yappr_shared::database::get_database_connection()
        .await
        .map_err(|e| {
            error!(error = %e, "Failed to connect to database");
            JobError::ExecutionError(format!("Database connection failed: {}", e))
        })?;

    // Fetch channel from database
    let progress = JobProgress {
        job_id: request.job_id.clone(),
        worker_id: worker_id.to_string(),
        progress: JobState::InProgress(25),
        message: format!("Fetching channel {}", request.channel_id),
    };
    let progress_bytes = rmp_serde::to_vec(&progress)?;
    client
        .publish(progress_subject.clone(), progress_bytes.into())
        .await
        .map_err(|e| JobError::RequestError(e.into()))?;

    let channel = ChannelService::get_channel_by_id(&db, request.channel_id)
        .await
        .map_err(|e| {
            error!(error = %e, channel_id = request.channel_id, "Failed to fetch channel");
            JobError::ExecutionError(format!("Channel fetch failed: {}", e))
        })?
        .ok_or_else(|| {
            error!(channel_id = request.channel_id, "Channel not found");
            JobError::ExecutionError("Channel not found".to_string())
        })?;

    info!(
        channel_id = request.channel_id,
        platform = %channel.platform_name,
        platform_channel_id = %channel.platform_channel_id,
        "Channel fetched successfully"
    );

    // Create appropriate platform API client
    let progress = JobProgress {
        job_id: request.job_id.clone(),
        worker_id: worker_id.to_string(),
        progress: JobState::InProgress(40),
        message: format!("Connecting to {} API", channel.platform_name),
    };
    let progress_bytes = rmp_serde::to_vec(&progress)?;
    client
        .publish(progress_subject.clone(), progress_bytes.into())
        .await
        .map_err(|e| JobError::RequestError(e.into()))?;

    let api_client: PlatformApiClient = match channel.platform_name.as_str() {
        "twitch" => {
            let twitch_client = TwitchApiClient::new().await.map_err(|e| {
                error!(error = %e, "Failed to create Twitch API client");
                JobError::ExecutionError(format!("Twitch API client creation failed: {}", e))
            })?;
            PlatformApiClient::Twitch(twitch_client)
        }
        "youtube" => {
            let youtube_client = YouTubeApiClient::new().await.map_err(|e| {
                error!(error = %e, "Failed to create YouTube API client");
                JobError::ExecutionError(format!("YouTube API client creation failed: {}", e))
            })?;
            PlatformApiClient::YouTube(youtube_client)
        }
        platform => {
            error!(platform = platform, "Unsupported platform");
            return Err(JobError::ExecutionError(format!(
                "Unsupported platform: {}",
                platform
            )));
        }
    };

    // Fetch recent videos from platform API
    let progress = JobProgress {
        job_id: request.job_id.clone(),
        worker_id: worker_id.to_string(),
        progress: JobState::InProgress(60),
        message: format!(
            "Fetching {} videos from API for channel {}",
            request.limit, channel.platform_channel_id
        ),
    };
    let progress_bytes = rmp_serde::to_vec(&progress)?;
    client
        .publish(progress_subject.clone(), progress_bytes.into())
        .await
        .map_err(|e| JobError::RequestError(e.into()))?;

    let videos = api_client
        .get_recent_videos_by_channel_id(&channel.platform_channel_id, request.limit)
        .await
        .map_err(|e| {
            error!(error = %e, "Failed to fetch videos from platform API");
            JobError::ExecutionError(format!("Platform API fetch failed: {}", e))
        })?;

    debug!(
        job_id = %request.job_id,
        channel_id = request.channel_id,
        fetched_count = videos.len(),
        "Videos fetched successfully"
    );

    // Send final completion progress
    let final_progress = JobProgress {
        job_id: request.job_id.clone(),
        worker_id: worker_id.to_string(),
        progress: JobState::Completed,
        message: format!("Fetched {} videos successfully", videos.len()),
    };
    let progress_bytes = rmp_serde::to_vec(&final_progress)?;
    client
        .publish(progress_subject, progress_bytes.into())
        .await
        .map_err(|e| JobError::RequestError(e.into()))?;

    // Return response with video data (orchestrator will handle DB saves)
    let fetched_count = videos.len() as u32;
    let response = FetchVideosResponse {
        job_id: request.job_id.clone(),
        videos,
        fetched_count,
    };

    debug!(
        job_id = %request.job_id,
        fetched_count = response.fetched_count,
        "Fetch videos job completed"
    );

    Ok(response)
}

/// Handle an update videos job - validates/updates existing videos via platform API
#[instrument(skip(client))]
pub async fn handle_update_videos_job(
    client: &Client,
    request: UpdateVideosJob,
) -> Result<UpdateVideosResponse, JobError> {
    info!(
        job_id = %request.job_id,
        video_count = request.video_ids.len(),
        platform = %request.platform,
        "Starting update videos job"
    );

    let progress_subject = format!("worker.progress.{}", request.job_id);
    let worker_id = "worker-1"; // TODO: Get from config or generate unique ID

    // Publish initial progress
    let progress = JobProgress {
        job_id: request.job_id.clone(),
        worker_id: worker_id.to_string(),
        progress: JobState::InProgress(10),
        message: "Connecting to database".to_string(),
    };
    let progress_bytes = rmp_serde::to_vec(&progress)?;
    client
        .publish(progress_subject.clone(), progress_bytes.into())
        .await
        .map_err(|e| JobError::RequestError(e.into()))?;

    // Connect to database
    let db = yappr_shared::database::get_database_connection()
        .await
        .map_err(|e| {
            error!(error = %e, "Failed to connect to database");
            JobError::ExecutionError(format!("Database connection failed: {}", e))
        })?;

    // Fetch all requested videos from database
    let progress = JobProgress {
        job_id: request.job_id.clone(),
        worker_id: worker_id.to_string(),
        progress: JobState::InProgress(25),
        message: format!("Fetching {} videos from database", request.video_ids.len()),
    };
    let progress_bytes = rmp_serde::to_vec(&progress)?;
    client
        .publish(progress_subject.clone(), progress_bytes.into())
        .await
        .map_err(|e| JobError::RequestError(e.into()))?;

    let mut videos = Vec::new();
    for video_id in &request.video_ids {
        if let Ok(Some(video)) = VideoService::get_by_id(&db, *video_id).await {
            videos.push(video);
        }
    }

    info!(
        job_id = %request.job_id,
        requested_count = request.video_ids.len(),
        found_count = videos.len(),
        "Fetched videos from database"
    );

    // Extract platform video IDs from platform_ref (format: "platform:video_id")
    let platform_video_ids: Vec<String> = videos
        .iter()
        .filter_map(|v| v.platform_ref.split(':').nth(1).map(|id| id.to_string()))
        .collect();

    // Create platform ID -> database video ID mapping
    let mut platform_to_db_map: HashMap<String, i32> = HashMap::new();
    for video in &videos {
        if let Some(platform_id) = video.platform_ref.split(':').nth(1) {
            platform_to_db_map.insert(platform_id.to_string(), video.id);
        }
    }

    // Create appropriate platform API client
    let progress = JobProgress {
        job_id: request.job_id.clone(),
        worker_id: worker_id.to_string(),
        progress: JobState::InProgress(40),
        message: format!("Connecting to {} API", request.platform),
    };
    let progress_bytes = rmp_serde::to_vec(&progress)?;
    client
        .publish(progress_subject.clone(), progress_bytes.into())
        .await
        .map_err(|e| JobError::RequestError(e.into()))?;

    let api_client: PlatformApiClient = match request.platform.as_str() {
        "twitch" => {
            let twitch_client = TwitchApiClient::new().await.map_err(|e| {
                error!(error = %e, "Failed to create Twitch API client");
                JobError::ExecutionError(format!("Twitch API client creation failed: {}", e))
            })?;
            PlatformApiClient::Twitch(twitch_client)
        }
        "youtube" => {
            let youtube_client = YouTubeApiClient::new().await.map_err(|e| {
                error!(error = %e, "Failed to create YouTube API client");
                JobError::ExecutionError(format!("YouTube API client creation failed: {}", e))
            })?;
            PlatformApiClient::YouTube(youtube_client)
        }
        platform => {
            error!(platform = platform, "Unsupported platform");
            return Err(JobError::ExecutionError(format!(
                "Unsupported platform: {}",
                platform
            )));
        }
    };

    // Fetch current video metadata from platform API
    let progress = JobProgress {
        job_id: request.job_id.clone(),
        worker_id: worker_id.to_string(),
        progress: JobState::InProgress(60),
        message: format!(
            "Fetching {} videos from {} API",
            platform_video_ids.len(),
            request.platform
        ),
    };
    let progress_bytes = rmp_serde::to_vec(&progress)?;
    client
        .publish(progress_subject.clone(), progress_bytes.into())
        .await
        .map_err(|e| JobError::RequestError(e.into()))?;

    let platform_videos = api_client
        .get_platform_videos_by_ids(&platform_video_ids)
        .await
        .map_err(|e| {
            error!(error = %e, "Failed to fetch videos from platform API");
            JobError::ExecutionError(format!("Platform API fetch failed: {}", e))
        })?;

    info!(
        job_id = %request.job_id,
        requested_count = platform_video_ids.len(),
        returned_count = platform_videos.len(),
        "Videos fetched from platform API"
    );

    // Determine which videos are missing (not returned by API)
    let returned_platform_ids: Vec<String> = platform_videos.iter().map(|v| v.id.clone()).collect();

    let missing_platform_ids: Vec<String> = platform_video_ids
        .iter()
        .filter(|id| !returned_platform_ids.contains(id))
        .cloned()
        .collect();

    let missing_video_ids: Vec<i32> = missing_platform_ids
        .iter()
        .filter_map(|platform_id| platform_to_db_map.get(platform_id).copied())
        .collect();

    debug!(
        job_id = %request.job_id,
        updated_count = platform_videos.len(),
        missing_count = missing_video_ids.len(),
        "Determined updated and missing videos"
    );

    // Send final completion progress
    let final_progress = JobProgress {
        job_id: request.job_id.clone(),
        worker_id: worker_id.to_string(),
        progress: JobState::Completed,
        message: format!(
            "Updated {} videos, {} missing",
            platform_videos.len(),
            missing_video_ids.len()
        ),
    };
    let progress_bytes = rmp_serde::to_vec(&final_progress)?;
    client
        .publish(progress_subject, progress_bytes.into())
        .await
        .map_err(|e| JobError::RequestError(e.into()))?;

    // Return response with updated videos and missing IDs (orchestrator will handle DB updates)
    let missing_count = missing_video_ids.len() as u32;
    let response = UpdateVideosResponse {
        job_id: request.job_id.clone(),
        updated_videos: platform_videos,
        missing_video_ids,
        updated_count: returned_platform_ids.len() as u32,
        missing_count,
    };

    info!(
        job_id = %request.job_id,
        updated_count = response.updated_count,
        missing_count = response.missing_count,
        "Update videos job completed"
    );

    Ok(response)
}
