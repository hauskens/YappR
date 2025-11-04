use crate::entities::sea_orm_active_enums::Videotype;
#[cfg(feature = "database")]
use crate::entities::video;
use crate::models::platforms::{PlatformVariant, VideoPlatform};
use crate::models::{FileStorage, FileStorageTrait};
use serde::de::Error;

pub trait Video {
    fn platform_variant(&self, platform: &VideoPlatform) -> PlatformVariant;
    fn video_url(&self, platform: &VideoPlatform) -> String;
}

impl Video for video::Model {
    fn platform_variant(&self, platform: &VideoPlatform) -> PlatformVariant {
        match self.video_type {
            Videotype::Vod => match platform {
                VideoPlatform::YouTube => PlatformVariant::YouTubeVideo,
                VideoPlatform::Twitch => PlatformVariant::TwitchVOD,
            },
            Videotype::Clip => match platform {
                VideoPlatform::YouTube => PlatformVariant::YouTubeClip,
                VideoPlatform::Twitch => PlatformVariant::TwitchClip,
            },
            _ => match platform {
                VideoPlatform::YouTube => PlatformVariant::YouTubeVideo,
                VideoPlatform::Twitch => PlatformVariant::TwitchClip,
            },
        }
    }
    fn video_url(&self, platform: &VideoPlatform) -> String {
        self.platform_variant(platform)
            .id_to_url(&self.platform_ref)
    }
}
impl FileStorageTrait for video::Model {
    fn get_file_storage(&self) -> Result<FileStorage, serde_json::Error> {
        let thumbnail = self
            .thumbnail
            .as_ref()
            .ok_or_else(|| serde_json::Error::custom("No thumbnail field"))?;

        // Check if thumbnail is null or empty
        if thumbnail.is_null() {
            return Err(serde_json::Error::custom("Thumbnail field is null"));
        }

        serde_json::from_value(thumbnail.clone()).map_err(|e| {
            serde_json::Error::custom(format!(
                "Failed to parse thumbnail JSON: {}. Value: {:?}",
                e, thumbnail
            ))
        })
    }
}
