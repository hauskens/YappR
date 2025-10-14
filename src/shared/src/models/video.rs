use crate::entities::sea_orm_active_enums::Videotype;
#[cfg(feature = "database")]
use crate::entities::video;
use crate::models::platforms::{PlatformVariant, VideoPlatform};

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
