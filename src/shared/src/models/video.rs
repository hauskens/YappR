#[cfg(feature = "database")]
use crate::entities::video;
use crate::models::platforms::{Platform, PlatformVariant};
use crate::entities::sea_orm_active_enums::Videotype;

pub trait Video {
    fn platform_variant(&self, platform: &Platform) -> PlatformVariant;
    fn video_url(&self, platform: &Platform) -> String;
    fn video_url_with_timestamp(&self, platform: &Platform, seconds: &u64) -> Result<String, Box<dyn std::error::Error>>;
}

impl Video for video::Model {
    fn platform_variant(&self, platform: &Platform) -> PlatformVariant {
        match self.video_type {
            Videotype::Vod => match platform {
                Platform::YouTube => PlatformVariant::YouTubeVideo,
                Platform::Twitch => PlatformVariant::TwitchVOD,
            },
            Videotype::Clip => match platform {
                Platform::YouTube => PlatformVariant::YouTubeClip,
                Platform::Twitch => PlatformVariant::TwitchClip,
            },
            _ => match platform {
                Platform::YouTube => PlatformVariant::YouTubeVideo,
                Platform::Twitch => PlatformVariant::TwitchClip,
            },
        }
    }
    fn video_url(&self, platform: &Platform) -> String {
        self.platform_variant(platform)
            .id_to_url(&self.platform_ref)
    }
    fn video_url_with_timestamp(&self, platform: &Platform, seconds: &u64) -> Result<String, Box<dyn std::error::Error>> {
        self.platform_variant(platform)
            .timestamp_url(&self.platform_ref, seconds)
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

    #[test]
    fn test_youtube_video() {
        let video = create_test_video(1, "dQw4w9WgXcQ", Videotype::Vod, 1);
        let platform = Platform::YouTube;

        assert_eq!(
            video.platform_variant(&platform),
            PlatformVariant::YouTubeVideo
        );
        assert_eq!(video.video_url(&platform), "https://youtube.com/watch?v=dQw4w9WgXcQ");
        assert_eq!(
            video.video_url_with_timestamp(&platform, &123).unwrap(),
            "https://youtube.com/watch?v=dQw4w9WgXcQ&t=123"
        );
    }


    #[test]
    fn test_twitch_vod() {
        let video = create_test_video(3, "1234567890", Videotype::Vod, 2);
        let platform = Platform::Twitch;

        assert_eq!(video.platform_variant(&platform), PlatformVariant::TwitchVOD);
        assert_eq!(video.video_url(&platform), "https://twitch.tv/videos/1234567890");
        assert_eq!(
            video.video_url_with_timestamp(&platform, &3600).unwrap(),
            "https://twitch.tv/videos/1234567890?t=01h00m00s"
        );
    }
}
