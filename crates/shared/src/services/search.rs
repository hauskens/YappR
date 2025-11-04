use crate::entities::{prelude::*, timestamp_mapping, video};
use crate::models::search::{SegmentsResult, VideoResult};
use chrono::{DateTime, Utc};
use sea_orm::{
    ColumnTrait, ConnectionTrait, DatabaseConnection, DbErr, EntityTrait, FromQueryResult,
    QueryFilter, Statement,
};
use std::collections::{HashMap, HashSet};
use tracing::{debug, info, instrument};

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

        if channel_ids.is_empty() {
            return Ok(Vec::new());
        }

        // Build SQL query - explicitly select segment columns (converting text_tsv to text)
        // plus video columns for manual parsing
        let mut sql = r#"
            SELECT
                s.id,
                s.text,
                s.start,
                s."end",
                s.previous_segment_id,
                s.next_segment_id,
                s.transcription_id,
                s.text_tsv::text as text_tsv,
                v.id as video_id,
                v.title as video_title,
                CAST(v.video_type AS TEXT) as video_type,
                v.duration as video_duration,
                v.channel_id as video_channel_id,
                v.last_updated as video_last_updated,
                v.platform_ref as video_platform_ref,
                v.thumbnail as video_thumbnail,
                v.audio as video_audio,
                v.uploaded as video_uploaded,
                v.active as video_active,
                v.estimated_upload_time as video_estimated_upload_time
            FROM segments s
            INNER JOIN transcriptions t ON s.transcription_id = t.id
            INNER JOIN video v ON t.video_id = v.id
            WHERE s.text_tsv @@ websearch_to_tsquery('simple', $1)
              AND v.channel_id = ANY($2)
              AND v.active = true
        "#
        .to_string();

        let mut params: Vec<sea_orm::Value> = vec![search_term.into(), channel_ids.into()];

        // Add date range filter if provided
        if let (Some(start), Some(end)) = (start_date, end_date) {
            sql.push_str(" AND v.uploaded >= $3 AND v.uploaded <= $4");
            params.push(start.into());
            params.push(end.into());
        }

        sql.push_str(" ORDER BY t.id, s.start LIMIT 6000");

        // Execute single query with all data
        let query_results = db
            .query_all(Statement::from_sql_and_values(
                sea_orm::DatabaseBackend::Postgres,
                &sql,
                params,
            ))
            .await?;

        if query_results.is_empty() {
            return Ok(Vec::new());
        }

        // Parse results - segments via ORM, videos manually
        let mut segment_results = Vec::new();
        let mut video_map: HashMap<i32, video::Model> = HashMap::new();
        let mut transcription_to_video: HashMap<i32, i32> = HashMap::new();

        for row in query_results {
            // Let SeaORM parse the segment from the row (s.* columns)
            let segment = crate::entities::segments::Model::from_query_result(&row, "")?;

            // Manually parse video columns
            let video_id: i32 = row.try_get("", "video_id")?;
            let transcription_id = segment.transcription_id;

            transcription_to_video.insert(transcription_id, video_id);

            if let std::collections::hash_map::Entry::Vacant(e) = video_map.entry(video_id) {
                let video = video::Model {
                    id: video_id,
                    title: row.try_get("", "video_title")?,
                    video_type: row.try_get("", "video_type")?,
                    duration: row.try_get("", "video_duration")?,
                    channel_id: row.try_get("", "video_channel_id")?,
                    last_updated: row.try_get("", "video_last_updated")?,
                    platform_ref: row.try_get("", "video_platform_ref")?,
                    thumbnail: row.try_get("", "video_thumbnail")?,
                    audio: row.try_get("", "video_audio")?,
                    uploaded: row.try_get("", "video_uploaded")?,
                    active: row.try_get("", "video_active")?,
                    estimated_upload_time: row.try_get("", "video_estimated_upload_time")?,
                };
                e.insert(video);
            }

            segment_results.push(segment);
        }

        // Sanitize search term to get individual words
        let search_words: Vec<String> = Self::sanitize_sentence(search_term);

        // Extract video IDs for timestamp mapping lookup
        let video_ids: Vec<i32> = video_map.keys().copied().collect();

        // Batch load timestamp mappings in ONE query
        let timestamp_mappings = TimestampMapping::find()
            .filter(timestamp_mapping::Column::SourceVideoId.is_in(video_ids))
            .filter(timestamp_mapping::Column::Active.eq(true))
            .all(db)
            .await?;

        // Group mappings by source_video_id for O(1) lookups
        let mappings_by_video: HashMap<i32, Vec<_>> =
            timestamp_mappings
                .into_iter()
                .fold(HashMap::new(), |mut acc, mapping| {
                    acc.entry(mapping.source_video_id)
                        .or_default()
                        .push(mapping);
                    acc
                });

        // Process results and group by video using HashMap lookups (no more DB queries!)
        let mut video_results: Vec<VideoResult> = Vec::new();
        let mut video_lookup: HashMap<i32, usize> = HashMap::new();
        let mut processed_segments: HashSet<(i32, i32)> = HashSet::new();

        for segment in segment_results {
            // Skip duplicates - use (transcription_id, start_time) as key
            let segment_key = (segment.transcription_id, segment.start);
            if processed_segments.contains(&segment_key) {
                continue;
            }
            processed_segments.insert(segment_key);

            // Look up video using the transcription_to_video map
            let video_id = match transcription_to_video.get(&segment.transcription_id) {
                Some(id) => *id,
                None => {
                    debug!(
                        transcription_id = segment.transcription_id,
                        "Transcription mapping not found, skipping segment"
                    );
                    continue;
                }
            };

            let video = match video_map.get(&video_id) {
                Some(v) => v,
                None => {
                    debug!(
                        video_id = video_id,
                        "Video not found in map, skipping segment"
                    );
                    continue;
                }
            };

            // Skip inactive videos early
            if !video.active {
                continue;
            }

            // Check for timestamp mappings (currently not fully implemented)
            // Note: Timestamp translation logic would go here when implemented
            let target_video = if let Some(_mappings) = mappings_by_video.get(&video.id) {
                // TODO: Implement timestamp translation
                // For now, just use the source video
                video
            } else {
                video
            };

            // Create segment result
            let segment_result =
                SegmentsResult::new(vec![segment], target_video.clone(), search_words.clone());

            // Add to video results
            if let Some(&index) = video_lookup.get(&target_video.id) {
                // Check for duplicate timestamps efficiently
                let segment_start = segment_result.start_time();
                let has_duplicate = video_results[index]
                    .segment_results
                    .iter()
                    .any(|r| r.start_time() == segment_start);

                if !has_duplicate {
                    video_results[index].segment_results.push(segment_result);
                }
            } else {
                let new_video_result = VideoResult::new(vec![segment_result], target_video.clone());
                video_lookup.insert(target_video.id, video_results.len());
                video_results.push(new_video_result);
            }
        }

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
