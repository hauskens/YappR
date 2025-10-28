use crate::entities::{prelude::*, segments};
use crate::models::platforms::VideoPlatform;
use sea_orm::{ColumnTrait, DatabaseConnection, DbErr, EntityTrait, QueryFilter};
use tracing::{info, instrument};

/// Service for segment-related operations
pub struct SegmentService;

impl SegmentService {
    /// Get a segment by its ID
    #[instrument(level = "info", skip(db))]
    pub async fn get_by_id(db: &DatabaseConnection, segment_id: i32) -> Result<segments::Model, DbErr> {
        info!(segment_id = segment_id, "Fetching segment by ID");

        Segments::find_by_id(segment_id)
            .one(db)
            .await?
            .ok_or(DbErr::RecordNotFound(format!("Segment {} not found", segment_id)))
    }

    /// Get URL with timestamp for a segment
    ///
    /// # Arguments
    /// * `video` - The video containing this segment
    /// * `platform_ref` - Platform reference ID for the video
    /// * `platform` - The video platform (YouTube or Twitch)
    /// * `segment_start` - Start time of the segment in seconds
    /// * `time_shift` - Number of seconds to shift backwards (default 5)
    pub fn get_url_timestamped(
        video_platform_ref: &str,
        platform: VideoPlatform,
        segment_start: i32,
        time_shift: i32,
    ) -> String {
        // Shift time backwards, but don't go below 0
        let shifted_time = (segment_start - time_shift).max(0) as u64;

        platform.timestamp_url(video_platform_ref, &shifted_time)
    }

    /// Get URL with timestamp for a segment model
    /// Requires the video to be loaded via relationship
    #[instrument(level = "info", skip(db, segment), fields(segment_id = segment.id))]
    pub async fn get_url_timestamped_from_segment(
        db: &DatabaseConnection,
        segment: &segments::Model,
        time_shift: i32,
    ) -> Result<String, DbErr> {
        info!(
            segment_id = segment.id,
            transcription_id = segment.transcription_id,
            "Generating timestamped URL for segment"
        );

        // Load the transcription to get the video
        let transcription = Transcriptions::find_by_id(segment.transcription_id)
            .one(db)
            .await?
            .ok_or(DbErr::RecordNotFound(format!(
                "Transcription {} not found",
                segment.transcription_id
            )))?;

        // Load the video
        let video = Video::find_by_id(transcription.video_id)
            .one(db)
            .await?
            .ok_or(DbErr::RecordNotFound(format!(
                "Video {} not found",
                transcription.video_id
            )))?;

        // Load the channel to get platform info
        let channel = Channels::find_by_id(video.channel_id)
            .one(db)
            .await?
            .ok_or(DbErr::RecordNotFound(format!(
                "Channel {} not found",
                video.channel_id
            )))?;

        // Determine platform from channel
        let platform = VideoPlatform::get_from_str(&channel.platform_name)
            .ok_or(DbErr::Custom(format!(
                "Invalid platform: {}",
                channel.platform_name
            )))?;

        Ok(Self::get_url_timestamped(
            &video.platform_ref,
            platform,
            segment.start,
            time_shift,
        ))
    }

    /// Get segments sorted by start time for a transcription
    #[instrument(level = "info", skip(db))]
    pub async fn get_segments_for_transcription(
        db: &DatabaseConnection,
        transcription_id: i32,
        descending: bool,
    ) -> Result<Vec<segments::Model>, DbErr> {
        info!(
            transcription_id = transcription_id,
            descending = descending,
            "Fetching segments for transcription"
        );

        let mut segments = Segments::find()
            .filter(segments::Column::TranscriptionId.eq(transcription_id))
            .all(db)
            .await?;

        // Sort by start time
        segments.sort_by(|a, b| {
            if descending {
                b.start.cmp(&a.start)
            } else {
                a.start.cmp(&b.start)
            }
        });

        Ok(segments)
    }

    /// Get adjacent segments (previous and next) for a segment
    #[instrument(level = "info", skip(db, segment), fields(segment_id = segment.id))]
    pub async fn get_adjacent_segments(
        db: &DatabaseConnection,
        segment: &segments::Model,
    ) -> Result<(Option<segments::Model>, Option<segments::Model>), DbErr> {
        info!(
            segment_id = segment.id,
            "Fetching adjacent segments"
        );

        let previous = if let Some(prev_id) = segment.previous_segment_id {
            Segments::find_by_id(prev_id).one(db).await?
        } else {
            None
        };

        let next = if let Some(next_id) = segment.next_segment_id {
            Segments::find_by_id(next_id).one(db).await?
        } else {
            None
        };

        Ok((previous, next))
    }

    /// Get segment duration in seconds
    pub fn get_duration(segment: &segments::Model) -> i32 {
        segment.end - segment.start
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_get_url_timestamped_youtube() {
        let url = SegmentService::get_url_timestamped(
            "dQw4w9WgXcQ",
            VideoPlatform::YouTube,
            100,
            5,
        );
        assert_eq!(url, "https://youtube.com/watch?v=dQw4w9WgXcQ&t=95");
    }

    #[test]
    fn test_get_url_timestamped_youtube_no_negative() {
        let url = SegmentService::get_url_timestamped(
            "dQw4w9WgXcQ",
            VideoPlatform::YouTube,
            3,
            5,
        );
        assert_eq!(url, "https://youtube.com/watch?v=dQw4w9WgXcQ&t=0");
    }

    #[test]
    fn test_get_url_timestamped_twitch() {
        let url = SegmentService::get_url_timestamped(
            "1234567890",
            VideoPlatform::Twitch,
            100,
            5,
        );
        assert_eq!(url, "https://twitch.tv/videos/1234567890?t=00h01m35s");
    }
}
