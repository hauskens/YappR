use crate::entities::{prelude::*, segments, transcriptions, video};
use crate::models::transcription::{SingleSegment, TranscriptionResult};
use chrono::{DateTime, Utc};
use sea_orm::{
    ActiveModelTrait, ColumnTrait, DatabaseConnection, DbErr, EntityTrait,
    PaginatorTrait, QueryFilter, QueryOrder, Set,
};
use serde_json;
use tracing::{info, instrument};

/// Service for transcription-related operations
pub struct TranscriptionService;

impl TranscriptionService {
    /// Get a transcription by its ID
    #[instrument(level = "info", skip(db))]
    pub async fn get_by_id(
        db: &DatabaseConnection,
        transcription_id: i32,
    ) -> Result<transcriptions::Model, DbErr> {
        info!(
            transcription_id = transcription_id,
            "Fetching transcription by ID"
        );

        Transcriptions::find_by_id(transcription_id)
            .one(db)
            .await?
            .ok_or(DbErr::RecordNotFound(format!(
                "Transcription {} not found",
                transcription_id
            )))
    }

    /// Get all transcriptions for a video
    #[instrument(level = "info", skip(db))]
    pub async fn get_by_video_id(
        db: &DatabaseConnection,
        video_id: i32,
    ) -> Result<Vec<transcriptions::Model>, DbErr> {
        info!(video_id = video_id, "Fetching transcriptions for video");

        Transcriptions::find()
            .filter(transcriptions::Column::VideoId.eq(video_id))
            .all(db)
            .await
    }

    /// Get total count of transcriptions
    #[instrument(level = "info", skip(db))]
    pub async fn get_count(db: &DatabaseConnection) -> Result<u64, DbErr> {
        Transcriptions::find().count(db).await
    }

    /// Get segments for a transcription sorted by start time
    #[instrument(level = "info", skip(db))]
    pub async fn get_segments_sorted(
        db: &DatabaseConnection,
        transcription: &transcriptions::Model,
        descending: bool,
    ) -> Result<Vec<segments::Model>, DbErr> {
        info!(
            transcription_id = transcription.id,
            descending = descending,
            "Fetching sorted segments for transcription"
        );

        let mut query = Segments::find()
            .filter(segments::Column::TranscriptionId.eq(transcription.id));

        query = if descending {
            query.order_by_desc(segments::Column::Start)
        } else {
            query.order_by_asc(segments::Column::Start)
        };

        query.all(db).await
    }

    /// Delete all segments attached to a transcription
    #[instrument(level = "info", skip(db))]
    pub async fn delete_attached_segments(
        db: &DatabaseConnection,
        transcription_id: i32,
    ) -> Result<u64, DbErr> {
        info!(
            transcription_id = transcription_id,
            "Deleting segments for transcription"
        );

        let result = Segments::delete_many()
            .filter(segments::Column::TranscriptionId.eq(transcription_id))
            .exec(db)
            .await?;

        info!(
            transcription_id = transcription_id,
            deleted_count = result.rows_affected,
            "Deleted segments"
        );

        Ok(result.rows_affected)
    }

    /// Reset a transcription by deleting segments and marking as unprocessed
    #[instrument(level = "info", skip(db))]
    pub async fn reset_transcription(
        db: &DatabaseConnection,
        transcription_id: i32,
    ) -> Result<(), DbErr> {
        info!(
            transcription_id = transcription_id,
            "Resetting transcription"
        );

        // Delete attached segments
        Self::delete_attached_segments(db, transcription_id).await?;

        // Mark as unprocessed
        let transcription = Self::get_by_id(db, transcription_id).await?;
        let mut active_model: transcriptions::ActiveModel = transcription.into();
        active_model.processed = Set(false);
        active_model.update(db).await?;

        Ok(())
    }

    /// Delete a transcription and all associated segments
    #[instrument(level = "info", skip(db))]
    pub async fn delete_transcription(
        db: &DatabaseConnection,
        transcription_id: i32,
    ) -> Result<(), DbErr> {
        info!(
            transcription_id = transcription_id,
            "Deleting transcription"
        );

        // Delete segments first
        Self::delete_attached_segments(db, transcription_id).await?;

        // Delete transcription
        let transcription = Self::get_by_id(db, transcription_id).await?;
        let active_model: transcriptions::ActiveModel = transcription.into();
        active_model.delete(db).await?;

        info!(
            transcription_id = transcription_id,
            "Transcription deleted"
        );

        Ok(())
    }

    /// Parse JSON transcription content and create segments
    #[instrument(level = "info", skip(db, json_content))]
    pub async fn parse_json(
        db: &DatabaseConnection,
        transcription_id: i32,
        json_content: &str,
    ) -> Result<Vec<segments::Model>, DbErr> {
        info!(
            transcription_id = transcription_id,
            "Parsing JSON transcription"
        );

        // Parse JSON
        let result: TranscriptionResult = serde_json::from_str(json_content)
            .map_err(|e| DbErr::Custom(format!("Failed to parse JSON: {}", e)))?;

        // Reset transcription first
        Self::reset_transcription(db, transcription_id).await?;

        let mut created_segments: Vec<segments::Model> = Vec::new();
        let mut previous_segment_id: Option<i32> = None;

        for caption in result.segments {
            let start = caption.start as i32;
            let end = caption.end as i32;
            let text = caption.text.trim();

            // Skip empty segments
            if text.is_empty() {
                continue;
            }

            // Skip duplicates if same as previous
            if let Some(_prev_id) = previous_segment_id
                && let Some(prev_seg) = created_segments.last()
                    && prev_seg.text == text {
                        continue;
                    }

            // Create new segment
            let new_segment = segments::ActiveModel {
                text: Set(text.to_string()),
                start: Set(start),
                end: Set(end),
                transcription_id: Set(transcription_id),
                previous_segment_id: Set(previous_segment_id),
                next_segment_id: Set(None),
                ..Default::default()
            };

            let inserted = new_segment.insert(db).await?;

            // Update previous segment's next_segment_id
            if let Some(prev_id) = previous_segment_id
                && let Some(prev_seg) = Segments::find_by_id(prev_id).one(db).await? {
                    let mut prev_active: segments::ActiveModel = prev_seg.into();
                    prev_active.next_segment_id = Set(Some(inserted.id));
                    prev_active.update(db).await?;
                }

            previous_segment_id = Some(inserted.id);
            created_segments.push(inserted);
        }

        // Mark as processed
        let transcription = Self::get_by_id(db, transcription_id).await?;
        let mut active_model: transcriptions::ActiveModel = transcription.into();
        active_model.processed = Set(true);
        active_model.update(db).await?;

        info!(
            transcription_id = transcription_id,
            segments_created = created_segments.len(),
            "JSON transcription parsed successfully"
        );

        Ok(created_segments)
    }

    /// Parse VTT transcription content and create segments
    /// VTT format: Each caption has start --> end timestamp and text
    #[instrument(level = "info", skip(db, vtt_content))]
    pub async fn parse_vtt(
        db: &DatabaseConnection,
        transcription_id: i32,
        vtt_content: &str,
    ) -> Result<Vec<segments::Model>, DbErr> {
        info!(
            transcription_id = transcription_id,
            "Parsing VTT transcription"
        );

        // Reset transcription first
        Self::reset_transcription(db, transcription_id).await?;

        let mut created_segments: Vec<segments::Model> = Vec::new();
        let mut previous_segment_id: Option<i32> = None;
        let mut previous_text: Option<String> = None;

        // Parse VTT - simple line-by-line parser
        let lines: Vec<&str> = vtt_content.lines().collect();
        let mut i = 0;
        // Remove annotations like [music]
        let re = regex::Regex::new(r"\[.*?\]").unwrap();

        // Skip header
        while i < lines.len() && !lines[i].contains("-->") {
            i += 1;
        }

        while i < lines.len() {
            let line = lines[i].trim();

            // Look for timestamp line (format: 00:00:00.000 --> 00:00:05.000)
            if line.contains("-->") {
                let parts: Vec<&str> = line.split("-->").collect();
                if parts.len() == 2 {
                    let start_str = parts[0].trim();
                    let end_str = parts[1].trim();

                    // Parse timestamps
                    if let (Ok(start), Ok(end)) =
                        (Self::parse_vtt_timestamp(start_str), Self::parse_vtt_timestamp(end_str))
                    {
                        // Get text from next line
                        i += 1;
                        if i < lines.len() {
                            let mut text = lines[i].trim().to_lowercase();

                            // Remove annotations like [music]
                            text = re.replace_all(&text, "").trim().to_string();

                            // Skip if empty or contains newline or duplicate
                            if text.is_empty() || text.contains('\n') {
                                i += 1;
                                continue;
                            }

                            if let Some(prev_text) = &previous_text
                                && prev_text == &text {
                                    i += 1;
                                    continue;
                                }

                            // Create segment
                            let new_segment = segments::ActiveModel {
                                text: Set(text.clone()),
                                start: Set(start),
                                end: Set(end),
                                transcription_id: Set(transcription_id),
                                previous_segment_id: Set(previous_segment_id),
                                next_segment_id: Set(None),
                                ..Default::default()
                            };

                            let inserted = new_segment.insert(db).await?;

                            // Update previous segment's next_segment_id
                            if let Some(prev_id) = previous_segment_id
                                && let Some(prev_seg) = Segments::find_by_id(prev_id).one(db).await?
                                {
                                    let mut prev_active: segments::ActiveModel = prev_seg.into();
                                    prev_active.next_segment_id = Set(Some(inserted.id));
                                    prev_active.update(db).await?;
                                }

                            previous_segment_id = Some(inserted.id);
                            previous_text = Some(text);
                            created_segments.push(inserted);
                        }
                    }
                }
            }
            i += 1;
        }

        // Mark as processed
        let transcription = Self::get_by_id(db, transcription_id).await?;
        let mut active_model: transcriptions::ActiveModel = transcription.into();
        active_model.processed = Set(true);
        active_model.update(db).await?;

        info!(
            transcription_id = transcription_id,
            segments_created = created_segments.len(),
            "VTT transcription parsed successfully"
        );

        Ok(created_segments)
    }

    /// Parse VTT timestamp (format: HH:MM:SS.mmm or MM:SS.mmm)
    fn parse_vtt_timestamp(timestamp: &str) -> Result<i32, String> {
        let parts: Vec<&str> = timestamp.split(':').collect();
        let seconds: i32;

        if parts.len() == 3 {
            // HH:MM:SS.mmm
            let hours: i32 = parts[0].parse().map_err(|e| format!("Invalid hours: {}", e))?;
            let minutes: i32 = parts[1].parse().map_err(|e| format!("Invalid minutes: {}", e))?;
            let secs_parts: Vec<&str> = parts[2].split('.').collect();
            let secs: i32 = secs_parts[0]
                .parse()
                .map_err(|e| format!("Invalid seconds: {}", e))?;

            seconds = hours * 3600 + minutes * 60 + secs;
        } else if parts.len() == 2 {
            // MM:SS.mmm
            let minutes: i32 = parts[0].parse().map_err(|e| format!("Invalid minutes: {}", e))?;
            let secs_parts: Vec<&str> = parts[1].split('.').collect();
            let secs: i32 = secs_parts[0]
                .parse()
                .map_err(|e| format!("Invalid seconds: {}", e))?;

            seconds = minutes * 60 + secs;
        } else {
            return Err(format!("Invalid timestamp format: {}", timestamp));
        }

        Ok(seconds)
    }

    /// Get transcriptions for all active videos on the given channels
    #[instrument(level = "info", skip(db, channel_ids))]
    pub async fn get_transcriptions_on_channels(
        db: &DatabaseConnection,
        channel_ids: Vec<i32>,
    ) -> Result<Vec<transcriptions::Model>, DbErr> {
        if channel_ids.is_empty() {
            return Ok(Vec::new());
        }

        info!(
            channel_count = channel_ids.len(),
            "Fetching transcriptions for channels"
        );

        let transcriptions = Transcriptions::find()
            .inner_join(Video)
            .filter(video::Column::ChannelId.is_in(channel_ids))
            .filter(video::Column::Active.eq(true))
            .all(db)
            .await?;

        info!(
            transcription_count = transcriptions.len(),
            "Found transcriptions"
        );

        Ok(transcriptions)
    }

    /// Get transcriptions for active videos on channels within a date range
    #[instrument(level = "info", skip(db, channel_ids))]
    pub async fn get_transcriptions_on_channels_daterange(
        db: &DatabaseConnection,
        channel_ids: Vec<i32>,
        start_date: DateTime<Utc>,
        end_date: DateTime<Utc>,
    ) -> Result<Vec<transcriptions::Model>, DbErr> {
        if channel_ids.is_empty() {
            return Ok(Vec::new());
        }

        info!(
            channel_count = channel_ids.len(),
            start_date = %start_date,
            end_date = %end_date,
            "Fetching transcriptions for channels in date range"
        );

        let transcriptions = Transcriptions::find()
            .inner_join(Video)
            .filter(video::Column::ChannelId.is_in(channel_ids))
            .filter(video::Column::Active.eq(true))
            .filter(video::Column::Uploaded.gte(start_date))
            .filter(video::Column::Uploaded.lte(end_date))
            .all(db)
            .await?;

        info!(
            transcription_count = transcriptions.len(),
            "Found transcriptions in date range"
        );

        Ok(transcriptions)
    }

    /// Convert transcription segments to JSON format
    pub fn to_json(segments: &[segments::Model], language: &str) -> Result<String, DbErr> {
        let json_segments: Vec<SingleSegment> = segments
            .iter()
            .map(|s| SingleSegment {
                start: s.start as f64,
                end: s.end as f64,
                text: s.text.clone(),
            })
            .collect();

        let result = TranscriptionResult {
            segments: json_segments,
            language: language.to_string(),
        };

        serde_json::to_string(&result)
            .map_err(|e| DbErr::Custom(format!("Failed to serialize to JSON: {}", e)))
    }

    /// Convert transcription segments to SRT format
    pub fn to_srt(segments: &[segments::Model]) -> String {
        let mut srt_content = Vec::new();

        for (i, segment) in segments.iter().enumerate() {
            let start_time = Self::format_srt_timestamp(segment.start);
            let end_time = Self::format_srt_timestamp(segment.end);

            srt_content.push(format!(
                "{}\n{} --> {}\n{}\n",
                i + 1,
                start_time,
                end_time,
                segment.text
            ));
        }

        srt_content.join("\n")
    }

    /// Format timestamp for SRT (HH:MM:SS,mmm)
    fn format_srt_timestamp(seconds: i32) -> String {
        let hours = seconds / 3600;
        let minutes = (seconds % 3600) / 60;
        let secs = seconds % 60;
        format!("{:02}:{:02}:{:02},000", hours, minutes, secs)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_vtt_timestamp() {
        assert_eq!(
            TranscriptionService::parse_vtt_timestamp("00:00:05.000"),
            Ok(5)
        );
        assert_eq!(
            TranscriptionService::parse_vtt_timestamp("00:01:30.000"),
            Ok(90)
        );
        assert_eq!(
            TranscriptionService::parse_vtt_timestamp("01:00:00.000"),
            Ok(3600)
        );
        assert_eq!(
            TranscriptionService::parse_vtt_timestamp("01:30.000"),
            Ok(90)
        );
    }

    #[test]
    fn test_format_srt_timestamp() {
        assert_eq!(
            TranscriptionService::format_srt_timestamp(5),
            "00:00:05,000"
        );
        assert_eq!(
            TranscriptionService::format_srt_timestamp(90),
            "00:01:30,000"
        );
        assert_eq!(
            TranscriptionService::format_srt_timestamp(3600),
            "01:00:00,000"
        );
    }
}
