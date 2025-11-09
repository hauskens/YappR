#[cfg(feature = "database")]
pub mod channel;
#[cfg(feature = "database")]
pub mod content_queue;
pub mod enums;
pub mod platforms;
#[cfg(feature = "database")]
pub mod search;
#[cfg(feature = "database")]
pub mod transcription;
#[cfg(feature = "database")]
pub mod user;
#[cfg(feature = "database")]
pub mod video;

use crate::config::Config;
use std::path::PathBuf;

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileStorage {
    pub content_path: Option<String>,
    pub filename: String,
    pub content_type: String,
    pub size: u64,
    pub files: Vec<String>,
    pub file_id: String,
    pub upload_storage: String,
    pub uploaded_at: String,
    pub path: String,
    pub url: String,
    pub saved: bool,
}

pub trait FileStorageTrait {
    fn get_file_storage(&self) -> Result<FileStorage, serde_json::Error>;
}

pub fn get_file(config: &Config, file_storage: &FileStorage) -> Result<PathBuf, std::io::Error> {
    let path = PathBuf::from(&config.storage_location).join(&file_storage.files[0]);
    if path.exists() {
        Ok(path)
    } else {
        Err(std::io::Error::new(
            std::io::ErrorKind::NotFound,
            format!("File does not exist: {}", path.display()),
        ))
    }
}
