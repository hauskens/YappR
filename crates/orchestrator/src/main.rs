use chrono::Utc;
use futures::StreamExt;
use sea_orm::{ActiveModelTrait, Set};
use std::collections::HashMap;
use tokio_cron_scheduler::{Job, JobScheduler};
use tracing::{error, info, instrument, warn};
use uuid::Uuid;
use yappr_shared::config::{Config, JobsConfig};
use yappr_shared::jobs::{
    FetchVideosJob, FetchVideosResponse, JobProgress, NatsClientExt, UpdateVideosJob,
    UpdateVideosResponse,
};
use yappr_shared::services::channel::ChannelService;
use yappr_shared::services::video::VideoService;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Initialize logging
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .init();

    info!("Starting YappR Orchestrator");

    // Load configuration
    let config = Config::load();
    let jobs_config = JobsConfig::load();

    info!(
        fetch_videos_enabled = jobs_config.fetch_videos.enabled,
        fetch_videos_schedule = %jobs_config.fetch_videos.schedule,
        update_videos_enabled = jobs_config.update_videos.enabled,
        update_videos_schedule = %jobs_config.update_videos.schedule,
        "Jobs configuration loaded"
    );

    // Connect to database
    let db = yappr_shared::database::get_database_connection().await?;
    info!("Database connection established");

    // Connect to NATS
    let nats_client = async_nats::connect(&config.nats.url.to_string()).await?;
    info!(nats_url = %config.nats.url.to_string(), "NATS connection established");

    // Create scheduler
    let mut scheduler = JobScheduler::new().await?;

    // Clone values for job closures
    let nats_fetch = nats_client.clone();
    let db_fetch = db.clone();
    let nats_update = nats_client.clone();
    let db_update = db.clone();

    // Register fetch_videos job if enabled
    if jobs_config.fetch_videos.enabled {
        info!(
            schedule = %jobs_config.fetch_videos.schedule,
            "Registering fetch_videos job"
        );

        // Get configuration for fetch job
        let channel_id: i32 = std::env::var("CHANNEL_ID")
            .expect("CHANNEL_ID environment variable must be set for fetch_videos job")
            .parse()
            .expect("CHANNEL_ID must be a valid integer");

        let video_limit: u32 = std::env::var("VIDEO_LIMIT")
            .unwrap_or_else(|_| "5".to_string())
            .parse()
            .unwrap_or(5);

        // Verify channel exists
        let channel = ChannelService::get_channel_by_id(&db, channel_id)
            .await?
            .ok_or_else(|| format!("Channel with ID {} not found", channel_id))?;

        info!(
            channel_id = channel_id,
            channel_name = %channel.name,
            platform = %channel.platform_name,
            video_limit = video_limit,
            "Fetch videos job configured"
        );

        let fetch_schedule = jobs_config.fetch_videos.schedule.clone();
        let fetch_job = Job::new_async(fetch_schedule.as_str(), move |uuid, _l| {
            info!(job_uuid = ?uuid, "Fetch videos job triggered by scheduler");
            let nats_client = nats_fetch.clone();
            let db = db_fetch.clone();

            Box::pin(async move {
                info!("Executing fetch_videos job");
                if let Err(e) = run_fetch_videos_job(nats_client, db, channel_id, video_limit).await
                {
                    error!(error = %e, "Failed to run fetch_videos job");
                }
            })
        })?;

        scheduler.add(fetch_job).await?;
        info!("Fetch videos job registered and added to scheduler");
    } else {
        info!("Fetch videos job is disabled");
    }

    // Register update_videos job if enabled
    if jobs_config.update_videos.enabled {
        info!(
            schedule = %jobs_config.update_videos.schedule,
            "Registering update_videos job"
        );

        let batch_size: u64 = std::env::var("UPDATE_BATCH_SIZE")
            .unwrap_or_else(|_| "50".to_string())
            .parse()
            .unwrap_or(50);

        info!(batch_size = batch_size, "Update videos job configured");

        let update_schedule = jobs_config.update_videos.schedule.clone();
        let update_job = Job::new_async(update_schedule.as_str(), move |uuid, _l| {
            info!(job_uuid = ?uuid, "Update videos job triggered by scheduler");
            let nats_client = nats_update.clone();
            let db = db_update.clone();

            Box::pin(async move {
                info!("Executing update_videos job");
                if let Err(e) = run_update_videos_job(nats_client, db, batch_size).await {
                    error!(error = %e, "Failed to run update_videos job");
                }
            })
        })?;

        scheduler.add(update_job).await?;
        info!("Update videos job registered and added to scheduler");
    } else {
        info!("Update videos job is disabled");
    }

    scheduler.start().await?;

    info!("Scheduler started, waiting for scheduled jobs...");
    info!("Press Ctrl+C to stop");

    // Keep the orchestrator running
    tokio::signal::ctrl_c().await?;

    info!("Shutting down orchestrator");
    scheduler.shutdown().await?;

    Ok(())
}

/// Run a single fetch job for the configured channel (fetch new/recent videos)
#[instrument(skip(nats_client, db))]
async fn run_fetch_videos_job(
    nats_client: async_nats::Client,
    db: sea_orm::DatabaseConnection,
    channel_id: i32,
    video_limit: u32,
) -> Result<(), Box<dyn std::error::Error>> {
    let job_id = Uuid::new_v4().to_string();

    info!(
        job_id = %job_id,
        channel_id = channel_id,
        video_limit = video_limit,
        "Starting fetch videos job"
    );

    // Subscribe to progress updates
    let progress_subject = format!("worker.progress.{}", job_id);
    let mut progress_subscriber = nats_client.subscribe(progress_subject.clone()).await?;

    // Spawn task to listen for progress updates
    let progress_task = tokio::spawn(async move {
        while let Some(message) = progress_subscriber.next().await {
            match rmp_serde::from_slice::<JobProgress>(&message.payload) {
                Ok(progress) => {
                    info!(
                        job_id = %progress.job_id,
                        worker_id = %progress.worker_id,
                        progress = %progress.progress,
                        message = %progress.message,
                        "Job progress update"
                    );
                }
                Err(e) => {
                    warn!(error = %e, "Failed to deserialize progress update");
                }
            }
        }
    });

    // Submit job to NATS
    let fetch_job = FetchVideosJob {
        job_id: job_id.clone(),
        channel_id,
        limit: video_limit,
    };

    info!(job_id = %job_id, "Submitting fetch videos job to NATS");

    // Send job and await response
    let response = nats_client.request_job(fetch_job).await?;

    info!(
        job_id = %job_id,
        fetched_count = response.fetched_count,
        "Received response from worker"
    );

    // Process and save videos to database
    save_videos_to_db(&db, channel_id, &response).await?;

    // Cancel progress listener
    progress_task.abort();

    info!(
        job_id = %job_id,
        saved_count = response.fetched_count,
        "Fetch videos job completed successfully"
    );

    Ok(())
}

/// Run update videos job - validates/updates oldest active videos across all platforms
#[instrument(skip(nats_client, db))]
async fn run_update_videos_job(
    nats_client: async_nats::Client,
    db: sea_orm::DatabaseConnection,
    batch_size: u64,
) -> Result<(), Box<dyn std::error::Error>> {
    info!(
        batch_size = batch_size,
        "Starting update videos job (validate/update oldest active videos)"
    );

    // Query oldest active videos for each platform
    let platforms = vec!["twitch", "youtube"];
    let mut total_updated = 0;
    let mut total_deactivated = 0;

    for platform in platforms {
        info!(platform = platform, "Processing platform");

        // Get oldest active videos for this platform
        let videos =
            VideoService::get_oldest_active_videos_by_platform(&db, platform, batch_size).await?;

        if videos.is_empty() {
            info!(platform = platform, "No active videos found for platform");
            continue;
        }

        info!(
            platform = platform,
            video_count = videos.len(),
            "Found active videos to update"
        );

        // Extract video IDs
        let video_ids: Vec<i32> = videos.iter().map(|v| v.id).collect();

        // Generate job ID
        let job_id = Uuid::new_v4().to_string();

        // Subscribe to progress updates
        let progress_subject = format!("worker.progress.{}", job_id);
        let mut progress_subscriber = nats_client.subscribe(progress_subject.clone()).await?;

        // Spawn task to listen for progress updates
        let progress_task = tokio::spawn(async move {
            while let Some(message) = progress_subscriber.next().await {
                match rmp_serde::from_slice::<JobProgress>(&message.payload) {
                    Ok(progress) => {
                        info!(
                            job_id = %progress.job_id,
                            worker_id = %progress.worker_id,
                            progress = %progress.progress,
                            message = %progress.message,
                            "Job progress update"
                        );
                    }
                    Err(e) => {
                        warn!(error = %e, "Failed to deserialize progress update");
                    }
                }
            }
        });

        // Submit update job to NATS
        let update_job = UpdateVideosJob {
            job_id: job_id.clone(),
            video_ids,
            platform: platform.to_string(),
        };

        info!(
            job_id = %job_id,
            platform = platform,
            "Submitting update videos job to NATS"
        );

        // Send job and await response
        let response = nats_client.request_job(update_job).await?;

        info!(
            job_id = %job_id,
            platform = platform,
            updated_count = response.updated_count,
            missing_count = response.missing_count,
            "Received response from worker"
        );

        // Process response: update videos and deactivate missing ones
        process_update_response(&db, &response).await?;

        total_updated += response.updated_count;
        total_deactivated += response.missing_count;

        // Cancel progress listener
        progress_task.abort();

        info!(
            platform = platform,
            updated = response.updated_count,
            deactivated = response.missing_count,
            "Platform processing completed"
        );
    }

    info!(
        total_updated = total_updated,
        total_deactivated = total_deactivated,
        "Update videos job completed successfully"
    );

    Ok(())
}

/// Save fetched videos to the database (insert new or update existing)
#[instrument(skip(db, response))]
async fn save_videos_to_db(
    db: &sea_orm::DatabaseConnection,
    channel_id: i32,
    response: &FetchVideosResponse,
) -> Result<(), Box<dyn std::error::Error>> {
    use yappr_shared::entities::video;

    let channel = ChannelService::get_channel_by_id(db, channel_id)
        .await?
        .ok_or_else(|| format!("Channel {} not found", channel_id))?;

    info!(
        channel_id = channel_id,
        video_count = response.videos.len(),
        "Saving videos to database"
    );

    let mut inserted = 0;
    let mut updated = 0;

    for platform_video in &response.videos {
        let platform_ref = format!("{}:{}", channel.platform_name, platform_video.id);

        // Check if video already exists
        let existing_video = VideoService::get_by_platform_ref(db, &platform_ref).await?;

        if let Some(existing) = existing_video {
            // Update existing video
            let mut active_video: video::ActiveModel = existing.into();
            active_video.title = Set(platform_video.title.clone());
            active_video.last_updated = Set(Utc::now().naive_utc());

            if let Some(duration) = platform_video.duration {
                active_video.duration = Set(duration.as_secs_f64());
            }

            if let Some(thumbnail_url) = &platform_video.thumbnail_url {
                active_video.thumbnail = Set(Some(serde_json::json!({"url": thumbnail_url})));
            }

            active_video.update(db).await?;
            updated += 1;

            info!(
                platform_ref = %platform_ref,
                title = %platform_video.title,
                "Updated existing video"
            );
        } else {
            // Insert new video
            let new_video = video::ActiveModel {
                title: Set(platform_video.title.clone()),
                video_type: Set(platform_video.video_type.clone()),
                duration: Set(platform_video
                    .duration
                    .map(|d| d.as_secs_f64())
                    .unwrap_or(0.0)),
                channel_id: Set(channel_id),
                last_updated: Set(Utc::now().naive_utc()),
                platform_ref: Set(platform_ref.clone()),
                thumbnail: Set(platform_video
                    .thumbnail_url
                    .as_ref()
                    .map(|url| serde_json::json!({"url": url}))),
                uploaded: Set(platform_video.created_at.naive_utc()),
                active: Set(true),
                audio: Set(None),
                estimated_upload_time: Set(None),
                ..Default::default()
            };

            new_video.insert(db).await?;
            inserted += 1;

            info!(
                platform_ref = %platform_ref,
                title = %platform_video.title,
                "Inserted new video"
            );
        }
    }

    info!(
        inserted = inserted,
        updated = updated,
        total = response.videos.len(),
        "Database save completed"
    );

    Ok(())
}

/// Process update response - update metadata for found videos, deactivate missing ones
#[instrument(skip(db, response))]
async fn process_update_response(
    db: &sea_orm::DatabaseConnection,
    response: &UpdateVideosResponse,
) -> Result<(), Box<dyn std::error::Error>> {
    info!(
        updated_count = response.updated_count,
        missing_count = response.missing_count,
        "Processing update response"
    );

    // Create a map of platform video ID -> PlatformVideo for quick lookup
    let mut video_map: HashMap<String, &yappr_shared::external::api_client::PlatformVideo> =
        HashMap::new();
    for platform_video in &response.updated_videos {
        video_map.insert(platform_video.id.clone(), platform_video);
    }

    // Update videos that were found
    for platform_video in &response.updated_videos {
        // Find the database video ID from the platform video ID
        // We need to query by platform_ref
        if let Ok(Some(db_video)) = VideoService::get_by_platform_ref(
            db,
            &format!(
                "{}:{}",
                response
                    .updated_videos
                    .first()
                    .map(|v| if v.id.chars().all(char::is_numeric) {
                        "twitch"
                    } else {
                        "youtube"
                    })
                    .unwrap_or("unknown"),
                platform_video.id
            ),
        )
        .await
        {
            // Update metadata
            let thumbnail = platform_video
                .thumbnail_url
                .as_ref()
                .map(|url| serde_json::json!({"url": url}));

            let duration = platform_video.duration.map(|d| d.as_secs_f64());

            VideoService::update_video_metadata(
                db,
                db_video.id,
                Some(platform_video.title.clone()),
                duration,
                thumbnail,
            )
            .await?;

            info!(
                video_id = db_video.id,
                title = %platform_video.title,
                "Updated video metadata"
            );
        }
    }

    // Deactivate missing videos
    for video_id in &response.missing_video_ids {
        VideoService::deactivate_video(db, *video_id).await?;

        info!(video_id = video_id, "Deactivated missing video");
    }

    info!("Update response processing completed");

    Ok(())
}
