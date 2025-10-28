use crate::entities::{segments, video};

/// Result containing segments that match a search query for a single video
#[derive(Debug, Clone)]
pub struct SegmentsResult {
    pub segments: Vec<segments::Model>,
    pub video: video::Model,
    pub search_words: Vec<String>,
}

impl SegmentsResult {
    pub fn new(segments: Vec<segments::Model>, video: video::Model, search_words: Vec<String>) -> Self {
        Self {
            segments,
            video,
            search_words,
        }
    }

    /// Get all segment texts concatenated into a single sentence
    pub fn get_sentences(&self) -> String {
        self.segments
            .iter()
            .map(|s| s.text.as_str())
            .collect::<Vec<&str>>()
            .join(" ")
    }

    /// Get formatted sentences with search words highlighted (uppercased)
    pub fn get_sentences_formatted(&self) -> String {
        let mut full_sentence = self.get_sentences();
        for word in &self.search_words {
            full_sentence = full_sentence.replace(word, &word.to_uppercase());
        }
        full_sentence
    }

    /// Get the start time of the earliest segment
    pub fn start_time(&self) -> i32 {
        self.segments
            .iter()
            .map(|s| s.start)
            .min()
            .unwrap_or(0)
    }

    /// Get the end time of the latest segment
    pub fn end_time(&self) -> i32 {
        self.segments
            .iter()
            .map(|s| s.end)
            .max()
            .unwrap_or(0)
    }

    /// Get the duration in seconds
    pub fn duration(&self) -> i32 {
        self.end_time() - self.start_time()
    }

    /// Get timestamped URL for the first segment
    /// Note: This will require the segment service to be implemented
    pub fn get_url(&self) -> Option<String> {
        self.segments.first().map(|segment| {
            // This will be implemented by SegmentService
            // For now, return a placeholder
            format!("video/{}/{}",  self.video.id, segment.start)
        })
    }
}

/// Collection of search results grouped by video
#[derive(Debug, Clone)]
pub struct VideoResult {
    pub segment_results: Vec<SegmentsResult>,
    pub video: video::Model,
}

impl VideoResult {
    pub fn new(segment_results: Vec<SegmentsResult>, video: video::Model) -> Self {
        Self {
            segment_results,
            video,
        }
    }

    /// Get total number of matching segments across all results
    pub fn total_segments(&self) -> usize {
        self.segment_results.iter().map(|r| r.segments.len()).sum()
    }

    /// Sort segment results by start time
    pub fn sort_by_time(&mut self) {
        self.segment_results.sort_by_key(|r| r.start_time());
    }
}
