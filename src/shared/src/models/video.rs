#[cfg(feature = "database")]
use crate::entities::video;
use crate::models::platforms::{VideoPlatform, PlatformVariant};
use crate::entities::sea_orm_active_enums::Videotype;

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

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;

    fn create_test_video(
        id: i32,
        platform_ref: &str,
        video_type: Videotype,
        channel_id: i32,
    ) -> video::Model {
        video::Model {
            id,
            title: format!("Test Video {}", id),
            video_type,
            duration: 300.0,
            channel_id,
            last_updated: Utc::now().naive_utc(),
            platform_ref: platform_ref.to_string(),
            thumbnail: None,
            audio: None,
            uploaded: Utc::now().naive_utc(),
            active: true,
            estimated_upload_time: None,
        }
    }
}
