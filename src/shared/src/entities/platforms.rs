use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Platform {
    YouTube,
    Twitch,
}

impl Platform {
    pub const ALL: &'static [Platform] = &[Platform::YouTube, Platform::Twitch];

    pub fn get_from_str(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "youtube" => Some(Platform::YouTube),
            "twitch" => Some(Platform::Twitch),
            _ => None,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            Platform::YouTube => "youtube",
            Platform::Twitch => "twitch",
        }
    }

    pub fn name(&self) -> &'static str {
        match self {
            Platform::YouTube => "YouTube",
            Platform::Twitch => "Twitch",
        }
    }

    pub fn base_url(&self) -> &'static str {
        match self {
            Platform::YouTube => "https://youtube.com",
            Platform::Twitch => "https://twitch.tv",
        }
    }

    pub fn primary_color(&self) -> &'static str {
        match self {
            Platform::YouTube => "#FF0000",
            Platform::Twitch => "#9146FF",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum PlatformVariant {
    YouTubeVideo,
    YouTubeShort,
    YouTubeClip,
    TwitchVOD,
    TwitchClip,
}

impl PlatformVariant {
    pub const ALL: &'static [PlatformVariant] = &[
        PlatformVariant::YouTubeVideo,
        PlatformVariant::YouTubeShort,
        PlatformVariant::YouTubeClip,
        PlatformVariant::TwitchVOD,
        PlatformVariant::TwitchClip,
    ];
    pub fn platform(&self) -> Platform {
        match self {
            PlatformVariant::YouTubeVideo => Platform::YouTube,
            PlatformVariant::YouTubeShort => Platform::YouTube,
            PlatformVariant::YouTubeClip => Platform::YouTube,
            PlatformVariant::TwitchVOD => Platform::Twitch,
            PlatformVariant::TwitchClip => Platform::Twitch,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            PlatformVariant::YouTubeVideo => "youtube_video",
            PlatformVariant::YouTubeShort => "youtube_short",
            PlatformVariant::YouTubeClip => "youtube_clip",
            PlatformVariant::TwitchVOD => "twitch_vod",
            PlatformVariant::TwitchClip => "twitch_clip",
        }
    }
    pub fn url_pattern(&self) -> &'static str {
        match self {
            PlatformVariant::YouTubeVideo => {
                r"^(?:https?://)?(?:www\.|m\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w\-]{11}(?:$|[&?])"
            }
            PlatformVariant::YouTubeShort => r"^(?:https?://)?(?:www.|m.)?youtube\.com/shorts/[\w\-]{11}(?:$|[&?])",
            PlatformVariant::YouTubeClip => r"^(?:https?://)?(?:www.|m.)?youtube\.com/clip/[\w\-]{36}(?:$|[&?])",
            PlatformVariant::TwitchVOD => r"^(?:https?://)?(?:www.|m.)?twitch\.tv/videos/\d{10}(?:$|[&?])",
            PlatformVariant::TwitchClip => r"^(?:https?://)?(?:www.|m.)?(?:clips\.twitch\.tv/[\w\-]+|twitch\.tv/\w+/clip/[\w\-]+)(?:$|[&?])",
        }
    }
    pub fn matches_url(&self, url: &str) -> bool {
        if url.contains("://") && !url.starts_with("http://") && !url.starts_with("https://") {
            return false;
        }
        regex::Regex::new(self.url_pattern()).unwrap().is_match(url)
    }

    pub fn from_url(url: &str) -> Option<Self> {
        for variant in Self::ALL {
            if variant.matches_url(url) {
                return Some(*variant);
            }
        }
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_platform_get_from_str() {
        assert_eq!(Platform::get_from_str("youtube"), Some(Platform::YouTube));
        assert_eq!(Platform::get_from_str("YouTube"), Some(Platform::YouTube));
        assert_eq!(Platform::get_from_str("YOUTUBE"), Some(Platform::YouTube));

        assert_eq!(Platform::get_from_str("twitch"), Some(Platform::Twitch));
        assert_eq!(Platform::get_from_str("Twitch"), Some(Platform::Twitch));
        assert_eq!(Platform::get_from_str("TWITCH"), Some(Platform::Twitch));

        assert_eq!(Platform::get_from_str("invalid"), None);
        assert_eq!(Platform::get_from_str("youtube_invalid"), None);
        assert_eq!(Platform::get_from_str(""), None);
    }

    #[test]
    fn test_youtube_video_variant_matches_url() {
        let valid_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&si=ESugKbhZOHe6PFbA",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&si=ESugKbhZOHe6PFbA&test=123",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&si=ESugKbhZOHe6PFbA&test=123&t=456",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ?si=ESugKbhZOHe6PFbA",
            "https://youtu.be/dQw4w9WgXcQ?feature=shared&t=44",
            "https://youtu.be/dQw4w9WgXcQ?feature=shared&t=44&si=ESugKbhZOHe6PFbA",
            "https://youtu.be/dQw4w9WgXcQ?feature=shared&t=44&si=ESugKbhZOHe6PFbA&test=123",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "youtube.com/watch?v=dQw4w9WgXcQ",
            "http://youtube.com/watch?v=dQw4w9WgXcQ",
            "http://youtube.com/watch?v=dQw4w9WgXcQ&si=ESugKbhZOHe6PFbA",
            "http://youtube.com/watch?v=dQw4w9WgXcQ&si=ESugKbhZOHe6PFbA&test=123",
            "http://youtube.com/watch?v=dQw4w9WgXcQ&si=ESugKbhZOHe6PFbA&test=123&t=456",
            "m.youtube.com/watch?v=dQw4w9WgXcQ",
            "m.youtube.com/watch?v=dQw4w9WgXcQ&si=ESugKbhZOHe6PFbA",
            "m.youtube.com/watch?v=dQw4w9WgXcQ&si=ESugKbhZOHe6PFbA&test=123",
            "m.youtube.com/watch?v=dQw4w9WgXcQ&si=ESugKbhZOHe6PFbA&test=123&t=456",
        ];

        let invalid_urls = [
            "https://twitch.tv/videos/123",
            "https://youtube.com/watch?v=test",
            "ftp://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQasdlkajsdlasljd",
        ];

        for url in valid_urls {
            assert!(
                PlatformVariant::YouTubeVideo.matches_url(url),
                "YouTube video URL should match: {}",
                url
            );
        }

        for url in invalid_urls {
            assert!(
                !PlatformVariant::YouTubeVideo.matches_url(url),
                "YouTube video URL should NOT match: {}",
                url
            );
        }
    }
    #[test]
    fn test_youtube_short_variant_matches_url() {
        let valid_urls = [
            "https://www.youtube.com/shorts/dQw4w9WgXcQ",
            "http://www.youtube.com/shorts/dQw4w9WgXcQ",
            "https://youtube.com/shorts/dQw4w9WgXcQ",
            "http://youtube.com/shorts/dQw4w9WgXcQ",
            "youtube.com/shorts/dQw4w9WgXcQ",
            "https://www.youtube.com/shorts/E_q2SjhawY0",
            "https://youtube.com/shorts/E_q2SjhawY0?feature=shared",
            "m.youtube.com/shorts/dQw4w9WgXcQ",
            "m.youtube.com/shorts/dQw4w9WgXcQ?si=ESugKbhZOHe6PFbA",
            "m.youtube.com/shorts/dQw4w9WgXcQ?si=ESugKbhZOHe6PFbA&test=123",
            "m.youtube.com/shorts/dQw4w9WgXcQ&si=ESugKbhZOHe6PFbA&test=123&t=456",
        ];

        let invalid_urls = [
            "https://twitch.tv/videos/123",
            "ftp://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com/shorts/dQw4w9WgXcasdlkjasldasjlk",
        ];

        for url in valid_urls {
            assert!(
                PlatformVariant::YouTubeShort.matches_url(url),
                "YouTube short URL should match: {}",
                url
            );
        }

        for url in invalid_urls {
            assert!(
                !PlatformVariant::YouTubeShort.matches_url(url),
                "YouTube short URL should NOT match: {}",
                url
            );
        }
    }
    #[test]
    fn test_youtube_clip_variant_matches_url() {
        let valid_urls = [
            "https://www.youtube.com/clip/UgkxFyeXQtfPRff43kUWbsAeuBND6Lb4ysEM",
            "http://www.youtube.com/clip/UgkxFyeXQtfPRff43kUWbsAeuBND6Lb4ysEM",
            "https://youtube.com/clip/UgkxFyeXQtfPRff43kUWbsAeuBND6Lb4ysEM",
            "http://youtube.com/clip/UgkxFyeXQtfPRff43kUWbsAeuBND6Lb4ysEM",
            "youtube.com/clip/UgkxFyeXQtfPRff43kUWbsAeuBND6Lb4ysEM",
            "m.youtube.com/clip/UgkxFyeXQtfPRff43kUWbsAeuBND6Lb4ysEM",
            "https://youtube.com/clip/UgkxhANZ5PHqXaGMfg5qX-TDKX7Qn9UeDv5c?feature=shared",
        ];

        let invalid_urls = [
            "https://twitch.tv/videos/123",
            "https://www.youtube.com/shorts/dQw4w9WgXcasdlkjasldasjlk",
            "ftp://www.youtube.com/clip/UgkxFyeXQtfPRff43kUWbsAeuBND6Lb4ysEM",
        ];

        for url in valid_urls {
            assert!(
                PlatformVariant::YouTubeClip.matches_url(url),
                "YouTube clip URL should match: {}",
                url
            );
        }

        for url in invalid_urls {
            assert!(
                !PlatformVariant::YouTubeClip.matches_url(url),
                "YouTube clip URL should NOT match: {}",
                url
            );
        }
    }

    #[test]
    fn test_twitch_vod_variant_matches_url() {
        let valid_urls = [
            "https://www.twitch.tv/videos/1234567890",
            "http://www.twitch.tv/videos/1234567890",
            "https://twitch.tv/videos/1234567890",
            "http://twitch.tv/videos/1234567890",
            "https://www.twitch.tv/videos/3338399115",
            "https://www.twitch.tv/videos/3338399115?t=01h09m43s",
            "https://www.twitch.tv/videos/3338399115?t=01h09m43s&test=123",
            "m.twitch.tv/videos/3338399115?t=01h09m43s&test=123",
            "https://m.twitch.tv/videos/3338399115?t=01h09m43s&test=123",
            "twitch.tv/videos/1234567890",
        ];

        let invalid_urls = [
            "https://twitch.tv/videos/123",
            "https://twitch.com/videos/1234567890",
            "https://twitch.com/videos/12345678901234567890",
            "ftp://twitch.tv/videos/1234567890",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        ];

        for url in valid_urls {
            assert!(
                PlatformVariant::TwitchVOD.matches_url(url),
                "Twitch VOD URL should match: {}",
                url
            );
        }

        for url in invalid_urls {
            assert!(
                !PlatformVariant::TwitchVOD.matches_url(url),
                "Twitch VOD URL should NOT match: {}",
                url
            );
        }
    }

    #[test]
    fn test_twitch_clip_variant_matches_url() {
        let valid_urls = [
            "https://clips.twitch.tv/CleverClipName",
            "https://twitch.tv/broadcaster/clip/CleverClipName",
            "https://clips.twitch.tv/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR",
            "https://www.twitch.tv/brittt/clip/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR?filter=clips&range=all&sort=time",
            "www.twitch.tv/brittt/clip/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR",
            "https://www.twitch.tv/brittt/clip/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR",
            "twitch.tv/brittt/clip/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR",
            "https://m.twitch.tv/brittt/clip/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR",
            "m.twitch.tv/brittt/clip/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR",
        ];

        let invalid_urls = [
            "https://twitch.tv/videos/123",
            "https://twitch.com/videos/1234567890",
            "https://twitch.com/videos/12345678901234567890",
            "ftp://twitch.tv/videos/1234567890",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://clips.twitch.tv/broadcaster/clip/CleverClipName", // broacaster is not under clips.twitch.tv
            "https://www.twitch.tv/clip/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR", // missing /broadcaster
            "https://www.twitch.tv/brittt/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR", // missing /clip behind broadcaster

        ];

        for url in valid_urls {
            assert!(
                PlatformVariant::TwitchClip.matches_url(url),
                "Twitch Clip URL should match: {}",
                url
            );
        }

        for url in invalid_urls {
            assert!(
                !PlatformVariant::TwitchClip.matches_url(url),
                "Twitch Clip URL should NOT match: {}",
                url
            );
        }
    }
    #[test]
    fn test_platform_variant_from_url() {
        assert_eq!(
            PlatformVariant::from_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
            Some(PlatformVariant::YouTubeVideo)
        );
        assert_eq!(
            PlatformVariant::from_url("https://www.youtube.com/shorts/dQw4w9WgXcQ"),
            Some(PlatformVariant::YouTubeShort)
        );
        assert_eq!(
            PlatformVariant::from_url("https://www.youtube.com/clip/UgkxFyeXQtfPRff43kUWbsAeuBND6Lb4ysEM"),
            Some(PlatformVariant::YouTubeClip)
        );
        assert_eq!(
            PlatformVariant::from_url("https://www.twitch.tv/videos/123456789"),
            Some(PlatformVariant::TwitchVOD)
        );
        assert_eq!(
            PlatformVariant::from_url("https://clips.twitch.tv/CleverClipName"),
            Some(PlatformVariant::TwitchClip)
        );
        assert_eq!(
            PlatformVariant::from_url("https://invalid-site.com/video"),
            None
        );
        assert_eq!(PlatformVariant::from_url("not-a-url"), None);
    }
}
