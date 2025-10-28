use crate::entities::{prelude::*, timestamp_mapping};
use crate::models::search::{SegmentsResult, VideoResult};
use chrono::{DateTime, Utc};
use sea_orm::{ColumnTrait, DatabaseConnection, DbErr, EntityTrait, QueryFilter, Statement};
use std::collections::{HashMap, HashSet};
use tracing::{info, instrument};

/// Service for search operations
pub struct SearchService;

impl SearchService {
    /// Search for videos containing the given search term using PostgreSQL text search
    ///
    /// # Arguments
    /// * `db` - Database connection
    /// * `search_term` - Search query (supports quoted phrases for exact matching)
    /// * `channel_ids` - List of channel IDs to search within
    /// * `start_date` - Optional start date filter
    /// * `end_date` - Optional end date filter
    ///
    /// # Returns
    /// List of VideoResult containing matching segments grouped by video
    #[instrument(level = "info", skip(db))]
    pub async fn search(
        db: &DatabaseConnection,
        search_term: &str,
        channel_ids: Vec<i32>,
        start_date: Option<DateTime<Utc>>,
        end_date: Option<DateTime<Utc>>,
    ) -> Result<Vec<VideoResult>, DbErr> {
        let start_time = std::time::Instant::now();

        info!(
            search_term = search_term,
            channel_count = channel_ids.len(),
            "Starting search operation"
        );

        // Get transcriptions for the channels
        let transcriptions = if let (Some(start), Some(end)) = (start_date, end_date) {
            crate::services::transcription::TranscriptionService::get_transcriptions_on_channels_daterange(
                db,
                channel_ids,
                start,
                end,
            )
            .await?
        } else {
            crate::services::transcription::TranscriptionService::get_transcriptions_on_channels(
                db,
                channel_ids,
            )
            .await?
        };

        if transcriptions.is_empty() {
            info!("No transcriptions found for channels");
            return Ok(Vec::new());
        }

        let transcription_ids: Vec<i32> = transcriptions.iter().map(|t| t.id).collect();

        info!(
            transcription_count = transcriptions.len(),
            "Found transcriptions"
        );

        // Prepare search term for PostgreSQL text search
        let db_search_term = search_term.to_string();

        // Execute text search query using PostgreSQL's ts_vector matching
        // Note: Using raw SQL here since SeaORM doesn't have direct support for ts_vector matching
        let sql = r#"
            SELECT id, text, start, "end", previous_segment_id, next_segment_id, transcription_id
            FROM segments
            WHERE text_tsv @@ to_tsquery('simple', $1)
            AND transcription_id = ANY($2)
            ORDER BY transcription_id, start
            LIMIT 6000
            "#.to_string();

        let segment_results = Segments::find()
            .from_raw_sql(Statement::from_sql_and_values(
                sea_orm::DatabaseBackend::Postgres,
                &sql,
                vec![db_search_term.into(), transcription_ids.into()],
            ))
            .all(db)
            .await?;

        info!(
            segment_count = segment_results.len(),
            "Found matching segments"
        );

        // Sanitize search term to get individual words
        let search_words: Vec<String> = Self::sanitize_sentence(search_term);

        // Process results and group by video
        let mut video_results: Vec<VideoResult> = Vec::new();
        let mut video_lookup: HashMap<i32, usize> = HashMap::new();
        let mut processed_segments: HashSet<(i32, i32, i32, i32)> = HashSet::new();

        for segment in segment_results {
            // Create unique identifier for this segment
            let segment_key = (segment.id, segment.transcription_id, segment.start, segment.end);

            if processed_segments.contains(&segment_key) {
                continue; // Skip already processed segments
            }

            processed_segments.insert(segment_key);

            // Get the transcription to access the video
            let transcription = Transcriptions::find_by_id(segment.transcription_id)
                .one(db)
                .await?
                .ok_or(DbErr::RecordNotFound(format!(
                    "Transcription {} not found",
                    segment.transcription_id
                )))?;

            // Load the source video
            let source_video = Video::find_by_id(transcription.video_id)
                .one(db)
                .await?
                .ok_or(DbErr::RecordNotFound(format!(
                    "Video {} not found",
                    transcription.video_id
                )))?;

            // Check for timestamp mappings (video linking)
            let target_video = source_video.clone();
            let mut translated_segment = segment.clone();

            // Get timestamp mappings where this video is the source
            let mappings = TimestampMapping::find()
                .filter(timestamp_mapping::Column::SourceVideoId.eq(source_video.id))
                .filter(timestamp_mapping::Column::Active.eq(true))
                .all(db)
                .await?;

            if !mappings.is_empty() {
                if let Some(mapping) = mappings.first() {
                    // Load target video
                    if let Some(target) = Video::find_by_id(mapping.target_video_id).one(db).await? {
                        // Try to translate timestamps
                        // Note: Timestamp translation logic would go here
                        // For now, we'll use the source video
                        // TODO: Implement timestamp translation
                        let _ = target;  // Suppress warning
                    }
                }
            }

            // Create segment result
            let segment_result = SegmentsResult::new(
                vec![translated_segment],
                target_video.clone(),
                search_words.clone(),
            );

            // Add to video results
            if let Some(&index) = video_lookup.get(&target_video.id) {
                // Check if we already have a segment at this timestamp
                let existing_timestamps: HashSet<i32> = video_results[index]
                    .segment_results
                    .iter()
                    .map(|r| r.start_time())
                    .collect();

                let segment_start = segment_result.start_time();

                if !existing_timestamps.contains(&segment_start) {
                    video_results[index].segment_results.push(segment_result);
                }
            } else {
                let new_video_result = VideoResult::new(vec![segment_result], target_video.clone());
                video_lookup.insert(target_video.id, video_results.len());
                video_results.push(new_video_result);
            }
        }

        // Filter out inactive videos
        video_results.retain(|v| v.video.active);

        // Sort segment results within each video by start time
        for video_result in &mut video_results {
            video_result.sort_by_time();
        }

        // Sort video results by upload date (descending)
        video_results.sort_by(|a, b| b.video.uploaded.cmp(&a.video.uploaded));

        let duration = start_time.elapsed();
        info!(
            duration_ms = duration.as_millis(),
            result_count = video_results.len(),
            "Search completed"
        );

        Ok(video_results)
    }

    /// Sanitize a sentence into individual words (lowercase, alphanumeric only)
    fn sanitize_sentence(sentence: &str) -> Vec<String> {
        sentence
            .to_lowercase()
            .split_whitespace()
            .map(|word| {
                word.chars()
                    .filter(|c| c.is_alphanumeric())
                    .collect::<String>()
            })
            .filter(|word| !word.is_empty())
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sanitize_sentence() {
        let result = SearchService::sanitize_sentence("Hello, World! This is a test.");
        assert_eq!(result, vec!["hello", "world", "this", "is", "a", "test"]);

        let result2 = SearchService::sanitize_sentence("Test123 ABC-DEF");
        assert_eq!(result2, vec!["test123", "abcdef"]);
    }
}
