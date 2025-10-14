use crate::entities::{
    content, content_queue, content_queue_submissions, prelude::*, user_weights,
};
use crate::external::api_client::{ApiClient, PlatformVideo};
use crate::external::twitch::client::TwitchApiClient;
use crate::external::youtube::client::YouTubeApiClient;
use crate::models::platforms::PlatformVariant;
use sea_orm::{
    ActiveModelTrait, ColumnTrait, DatabaseConnection, DbErr, EntityTrait, QueryFilter, Set,
};
use std::error::Error;
use tracing::{info, instrument};

/// Service for handling content submission workflow
pub struct ContentSubmissionService;

impl ContentSubmissionService {
    /// Main entry point: Add URL to content queue
    ///
    /// # Arguments
    /// * `db` - Database connection
    /// * `url` - Video URL to submit
    /// * `broadcaster_id` - Broadcaster whose queue this is for
    /// * `submitter_user_id` - User who submitted the content
    /// * `submission_weight` - Weight of this submission (e.g., Discord reaction count)
    ///
    /// # Returns
    /// * `(content_queue::Model, bool)` - Queue entry and whether content was newly created
    #[instrument(level = "info", skip(db))]
    pub async fn submit_url(
        db: &DatabaseConnection,
        url: &str,
        broadcaster_id: i32,
        submitter_user_id: i32,
        submission_weight: f64,
    ) -> Result<(content_queue::Model, bool), Box<dyn Error>> {
        info!(
            url = url,
            broadcaster_id = broadcaster_id,
            user_id = submitter_user_id,
            "Processing content submission"
        );

        // Step 1: Parse URL and detect platform
        let (platform_variant, video_id) = Self::parse_platform_url(url)?;
        let stripped_url = platform_variant.standardized_url(url)?.to_string();

        // Step 2: Check if content already exists
        let (content_record, is_new_content) =
            match Self::get_content_by_url(db, &stripped_url).await? {
                Some(existing) => {
                    info!(content_id = existing.id, "Content already exists");
                    (existing, false)
                }
                None => {
                    // Step 3: Fetch metadata from platform API
                    let platform_video =
                        Self::fetch_platform_metadata(&platform_variant, &video_id).await?;

                    // Step 4: Create content record
                    let content_record =
                        Self::create_content(db, &platform_video, &stripped_url).await?;
                    info!(content_id = content_record.id, "Created new content");
                    (content_record, true)
                }
            };

        // Step 5: Check if queue entry already exists for this broadcaster
        let queue_entry = match Self::get_queue_entry(db, content_record.id, broadcaster_id).await?
        {
            Some(existing) => {
                info!(queue_id = existing.id, "Queue entry already exists");
                existing
            }
            None => {
                // Step 6: Calculate score
                let score =
                    Self::calculate_score(db, broadcaster_id, submitter_user_id, submission_weight)
                        .await?;

                // Step 7: Create queue entry
                Self::create_queue_entry(db, content_record.id, broadcaster_id, score).await?
            }
        };

        // Step 8: Record submission
        Self::record_submission(db, queue_entry.id, submitter_user_id, submission_weight).await?;

        Ok((queue_entry, is_new_content))
    }

    /// TODO: use platforms.rs logic instead
    /// Parse platform URL using existing platforms.rs logic
    fn parse_platform_url(url: &str) -> Result<(PlatformVariant, String), Box<dyn Error>> {
        let platform =
            PlatformVariant::from_url(url).ok_or("Unsupported platform or invalid URL")?;

        // Extract video ID from the URL based on platform type
        let video_id = match platform {
            PlatformVariant::YouTubeVideo => {
                // Extract from ?v= parameter or /watch/ path
                if let Some(start) = url.find("?v=") {
                    url[start + 3..].split('&').next().unwrap_or("").to_string()
                } else if let Some(start) = url.find("youtu.be/") {
                    url[start + 9..]
                        .split(&['?', '&'][..])
                        .next()
                        .unwrap_or("")
                        .to_string()
                } else {
                    return Err("Could not extract YouTube video ID".into());
                }
            }
            PlatformVariant::YouTubeShort | PlatformVariant::YouTubeClip => {
                // Extract from path
                url.split('/')
                    .last()
                    .and_then(|s| s.split('?').next())
                    .unwrap_or("")
                    .to_string()
            }
            PlatformVariant::TwitchVOD => {
                // Extract from /videos/ID
                url.split('/')
                    .last()
                    .and_then(|s| s.split('?').next())
                    .unwrap_or("")
                    .to_string()
            }
            PlatformVariant::TwitchClip => {
                // Extract from clips.twitch.tv/ID or /clip/ID
                url.split('/')
                    .last()
                    .and_then(|s| s.split('?').next())
                    .unwrap_or("")
                    .to_string()
            }
        };

        if video_id.is_empty() {
            return Err("Could not extract video ID from URL".into());
        }

        Ok((platform, video_id))
    }

    /// TODO: Box::new, maybe re-use client instead of creating new one each time
    /// Fetch video metadata from platform API
    #[instrument(level = "info", skip(platform))]
    async fn fetch_platform_metadata(
        platform: &PlatformVariant,
        video_id: &str,
    ) -> Result<PlatformVideo, Box<dyn Error>> {
        let client: Box<dyn ApiClient> = match platform {
            PlatformVariant::YouTubeVideo
            | PlatformVariant::YouTubeShort
            | PlatformVariant::YouTubeClip => Box::new(YouTubeApiClient::new().await?),
            PlatformVariant::TwitchVOD | PlatformVariant::TwitchClip => {
                Box::new(TwitchApiClient::new().await?)
            }
        };

        let mut videos = client
            .get_platform_videos_by_ids(&[video_id.to_string()])
            .await?;
        videos
            .pop()
            .ok_or_else(|| "Video not found on platform".into())
    }

    /// Get existing content by stripped URL
    async fn get_content_by_url(
        db: &DatabaseConnection,
        stripped_url: &str,
    ) -> Result<Option<content::Model>, DbErr> {
        Content::find()
            .filter(content::Column::StrippedUrl.eq(stripped_url))
            .one(db)
            .await
    }

    /// Create new content record
    #[instrument(level = "info", skip(db, platform_video))]
    async fn create_content(
        db: &DatabaseConnection,
        platform_video: &PlatformVideo,
        stripped_url: &str,
    ) -> Result<content::Model, DbErr> {
        let active_model = content::ActiveModel {
            url: Set(stripped_url.to_string()),
            stripped_url: Set(stripped_url.to_string()),
            title: Set(platform_video.title.clone()),
            author: Set(None),                // Platform API doesn't return author
            channel_name: Set(String::new()), // Would need separate channel fetch
            thumbnail_url: Set(platform_video.thumbnail_url.clone()),
            duration: Set(platform_video.duration.map(|d| d.as_secs() as i32)),
            created_at: Set(Some(chrono::Utc::now().naive_utc())),
            ..Default::default()
        };

        active_model.insert(db).await
    }

    /// Get existing queue entry
    async fn get_queue_entry(
        db: &DatabaseConnection,
        content_id: i32,
        broadcaster_id: i32,
    ) -> Result<Option<content_queue::Model>, DbErr> {
        ContentQueue::find()
            .filter(content_queue::Column::ContentId.eq(content_id))
            .filter(content_queue::Column::BroadcasterId.eq(broadcaster_id))
            .one(db)
            .await
    }

    /// Create queue entry
    #[instrument(level = "info", skip(db))]
    async fn create_queue_entry(
        db: &DatabaseConnection,
        content_id: i32,
        broadcaster_id: i32,
        score: f64,
    ) -> Result<content_queue::Model, DbErr> {
        let active_model = content_queue::ActiveModel {
            content_id: Set(content_id),
            broadcaster_id: Set(broadcaster_id),
            score: Set(score),
            watched: Set(false),
            watched_at: Set(None),
            skipped: Set(false),
            disabled: Set(false),
            content_timestamp: Set(None),
            ..Default::default()
        };

        active_model.insert(db).await
    }

    /// Record submission
    #[instrument(level = "info", skip(db))]
    async fn record_submission(
        db: &DatabaseConnection,
        queue_id: i32,
        user_id: i32,
        weight: f64,
    ) -> Result<content_queue_submissions::Model, DbErr> {
        // Get the content_id from the queue entry
        let queue_entry = ContentQueue::find_by_id(queue_id)
            .one(db)
            .await?
            .ok_or(DbErr::RecordNotFound("Queue entry not found".to_string()))?;

        let active_model = content_queue_submissions::ActiveModel {
            content_queue_id: Set(queue_id),
            content_id: Set(queue_entry.content_id),
            user_id: Set(user_id),
            weight: Set(weight),
            submitted_at: Set(chrono::Utc::now().naive_utc()),
            submission_source_type: Set(
                crate::entities::sea_orm_active_enums::Contentqueuesubmissionsource::Web,
            ), // TODO: Make this configurable
            submission_source_id: Set(0), // TODO: Make this configurable
            user_comment: Set(None),
            submission_source_ref: Set(None),
            ..Default::default()
        };

        active_model.insert(db).await
    }

    /// Calculate final score: submission_weight * user_weight
    #[instrument(level = "info", skip(db))]
    async fn calculate_score(
        db: &DatabaseConnection,
        broadcaster_id: i32,
        user_id: i32,
        submission_weight: f64,
    ) -> Result<f64, DbErr> {
        // Get user's weight (default 1.0 if not found)
        let user_weight = UserWeights::find()
            .filter(user_weights::Column::UserId.eq(user_id))
            .filter(user_weights::Column::BroadcasterId.eq(broadcaster_id))
            .filter(user_weights::Column::Banned.eq(false))
            .one(db)
            .await?
            .map(|w| w.weight)
            .unwrap_or(1.0);

        let score = submission_weight * user_weight;
        info!(
            submission_weight = submission_weight,
            user_weight = user_weight,
            final_score = score,
            "Calculated score"
        );

        Ok(score)
    }
}
