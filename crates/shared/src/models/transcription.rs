use crate::entities::transcriptions;
use crate::models::{FileStorage, FileStorageTrait};
use serde::{Deserialize, Serialize};

/// A single segment (up to multiple sentences) of a speech.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SingleSegment {
    pub start: f64,
    pub end: f64,
    pub text: String,
}

impl SingleSegment {
    pub fn new(start: f64, end: f64, text: String) -> Self {
        Self { start, end, text }
    }

    pub fn duration(&self) -> f64 {
        self.end - self.start
    }
}

/// A list of segments and word segments of a speech.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TranscriptionResult {
    pub segments: Vec<SingleSegment>,
    pub language: String,
}

impl TranscriptionResult {
    pub fn new(segments: Vec<SingleSegment>, language: String) -> Self {
        Self { segments, language }
    }

    pub fn total_duration(&self) -> f64 {
        self.segments.iter().map(|s| s.duration()).sum()
    }

    pub fn segment_count(&self) -> usize {
        self.segments.len()
    }
}

impl FileStorageTrait for transcriptions::Model {
    fn get_file_storage(&self) -> Result<FileStorage, serde_json::Error> {
        serde_json::from_value(self.file.clone())
    }
}
