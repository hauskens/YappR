use crate::utils;
use hex_color::HexColor;
use serde::{Deserialize, Serialize};
use std::time::Duration;
use url::Url;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum BasePlatform {
    YouTube,
    Twitch,
    Discord,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum VideoPlatform {
    YouTube,
    Twitch,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum PlatformVariant {
    YouTubeVideo,
    YouTubeShort,
    YouTubeClip,
    TwitchVOD,
    TwitchClip,
}

impl BasePlatform {
    pub fn get_from_str(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "youtube" => Some(BasePlatform::YouTube),
            "twitch" => Some(BasePlatform::Twitch),
            "discord" => Some(BasePlatform::Discord),
            _ => None,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            BasePlatform::YouTube => "youtube",
            BasePlatform::Twitch => "twitch",
            BasePlatform::Discord => "discord",
        }
    }

    pub fn display_name(&self) -> &'static str {
        match self {
            BasePlatform::YouTube => "YouTube",
            BasePlatform::Twitch => "Twitch",
            BasePlatform::Discord => "Discord",
        }
    }

    pub fn base_url(&self) -> Url {
        match self {
            BasePlatform::YouTube => Url::parse("https://youtube.com").unwrap(),
            BasePlatform::Twitch => Url::parse("https://twitch.tv").unwrap(),
            BasePlatform::Discord => Url::parse("https://discord.com").unwrap(),
        }
    }

    pub fn primary_color(&self) -> HexColor {
        match self {
            BasePlatform::YouTube => HexColor::parse("#FF0000").unwrap(),
            BasePlatform::Twitch => HexColor::parse("#9146FF").unwrap(),
            BasePlatform::Discord => HexColor::parse("#7289DA").unwrap(),
        }
    }
    pub fn secondary_color(&self) -> HexColor {
        match self {
            BasePlatform::YouTube => HexColor::parse("#FFFFFF").unwrap(),
            BasePlatform::Twitch => HexColor::parse("#FFFFFF").unwrap(),
            BasePlatform::Discord => HexColor::parse("#FFFFFF").unwrap(),
        }
    }
    pub fn badge_url(&self) -> &'static str {
        match self {
            BasePlatform::YouTube => {
                "https://img.shields.io/badge/manage-6C757D?style=plastic&logo=youtube&logoColor=white&labelColor=FF0000"
            }
            BasePlatform::Twitch => {
                "https://img.shields.io/badge/manage-6C757D?style=plastic&logo=twitch&logoColor=white&labelColor=9147FF"
            }
            BasePlatform::Discord => {
                "https://img.shields.io/badge/manage-6C757D?style=plastic&logo=discord&logoColor=white&labelColor=7289DA"
            }
        }
    }
}

impl From<&VideoPlatform> for BasePlatform {
    fn from(value: &VideoPlatform) -> Self {
        match value {
            VideoPlatform::YouTube => BasePlatform::YouTube,
            VideoPlatform::Twitch => BasePlatform::Twitch,
        }
    }
}

impl From<&PlatformVariant> for BasePlatform {
    fn from(value: &PlatformVariant) -> Self {
        match value {
            PlatformVariant::YouTubeVideo => BasePlatform::YouTube,
            PlatformVariant::YouTubeShort => BasePlatform::YouTube,
            PlatformVariant::YouTubeClip => BasePlatform::YouTube,
            PlatformVariant::TwitchVOD => BasePlatform::Twitch,
            PlatformVariant::TwitchClip => BasePlatform::Twitch,
        }
    }
}

impl VideoPlatform {
    pub fn get_from_str(s: &str) -> Option<Self> {
        match BasePlatform::get_from_str(s)? {
            BasePlatform::YouTube => Some(VideoPlatform::YouTube),
            BasePlatform::Twitch => Some(VideoPlatform::Twitch),
            _ => None,
        }
    }
    pub fn get_base_platform(&self) -> BasePlatform {
        BasePlatform::from(self)
    }
    pub fn video_url(&self, video_ref: &str) -> Url {
        match self {
            VideoPlatform::YouTube => {
                let mut url = BasePlatform::YouTube.base_url().join("/watch").unwrap();
                url.query_pairs_mut().append_pair("v", video_ref);
                url
            }
            VideoPlatform::Twitch => BasePlatform::Twitch
                .base_url()
                .join(&format!("/videos/{}", video_ref))
                .unwrap(),
        }
    }

    pub fn as_str(&self) -> &'static str {
        self.get_base_platform().as_str()
    }

    pub fn extract_timestamp(&self, url: &str) -> Option<u64> {
        let parsed_url = Url::parse(url).unwrap();
        match self {
            VideoPlatform::YouTube => {
                if let Some(query) = parsed_url.query() {
                    for pair in query.split('&') {
                        if let Some((key, value)) = pair.split_once('=')
                            && key == "t"
                        {
                            return Some(Duration::from_secs(value.parse().unwrap()).as_secs());
                        }
                    }
                }
                None
            }
            VideoPlatform::Twitch => {
                if let Some(query) = parsed_url.query() {
                    for pair in query.split('&') {
                        if let Some((key, value)) = pair.split_once('=')
                            && key == "t"
                        {
                            return Some(utils::parse_duration(value).unwrap().as_secs());
                        }
                    }
                }
                None
            }
        }
    }

    pub fn timestamp_url(&self, video_ref: &str, seconds_offset: &f64) -> Url {
        match self {
            VideoPlatform::YouTube => {
                let mut url = self.video_url(video_ref);
                url.query_pairs_mut()
                    .append_pair("t", seconds_offset.to_string().as_str());
                url
            }
            VideoPlatform::Twitch => {
                let timestamp = utils::format_timestamp_hms(&(seconds_offset.floor() as usize));
                let mut url = self.video_url(video_ref);
                url.query_pairs_mut().append_pair("t", timestamp.as_str());
                url
            }
        }
    }
}

impl PlatformVariant {
    pub const ALL: &'static [PlatformVariant] = &[
        PlatformVariant::YouTubeVideo,
        PlatformVariant::YouTubeShort,
        PlatformVariant::YouTubeClip,
        PlatformVariant::TwitchVOD,
        PlatformVariant::TwitchClip,
    ];

    pub fn base_platform(&self) -> BasePlatform {
        BasePlatform::from(self)
    }

    pub fn base_content_url(&self) -> Url {
        match self {
            PlatformVariant::YouTubeVideo => {
                BasePlatform::from(self).base_url().join("/watch").unwrap()
            }
            PlatformVariant::YouTubeShort => {
                BasePlatform::from(self).base_url().join("/shorts").unwrap()
            }
            PlatformVariant::YouTubeClip => {
                BasePlatform::from(self).base_url().join("/clip").unwrap()
            }
            PlatformVariant::TwitchVOD => {
                BasePlatform::from(self).base_url().join("/videos").unwrap()
            }
            PlatformVariant::TwitchClip => url::Url::parse("https://clips.twitch.tv").unwrap(),
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
            PlatformVariant::YouTubeShort => {
                r"^(?:https?://)?(?:www.|m.)?youtube\.com/shorts/[\w\-]{11}(?:$|[&?])"
            }
            PlatformVariant::YouTubeClip => {
                r"^(?:https?://)?(?:www.|m.)?youtube\.com/clip/[\w\-]{36}(?:$|[&?])"
            }
            PlatformVariant::TwitchVOD => {
                r"^(?:https?://)?(?:www.|m.)?twitch\.tv/videos/\d{10}(?:$|[&?])"
            }
            PlatformVariant::TwitchClip => {
                r"^(?:https?://)?(?:www.|m.)?(?:clips\.twitch\.tv/[\w\-]+|twitch\.tv/\w+/clip/[\w\-]+)(?:$|[&?])"
            }
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

    pub fn id_to_url(&self, id: &str) -> String {
        match self {
            PlatformVariant::YouTubeVideo => format!("{}?v={}", self.base_content_url(), id),
            PlatformVariant::YouTubeShort => format!("{}/{}", self.base_content_url(), id),
            PlatformVariant::YouTubeClip => format!("{}/{}", self.base_content_url(), id),
            PlatformVariant::TwitchVOD => format!("{}/{}", self.base_content_url(), id),
            PlatformVariant::TwitchClip => format!("{}{}", self.base_content_url(), id),
        }
    }

    pub fn standardized_url(&self, url: &str) -> Result<Url, url::ParseError> {
        let mut base_url = self.base_content_url();
        let parsed_url = Url::parse(url)?;
        match self {
            PlatformVariant::YouTubeVideo => {
                // First, try to extract from query parameter 'v='
                if let Some(query) = parsed_url.query() {
                    for pair in query.split('&') {
                        if let Some((key, value)) = pair.split_once('=')
                            && key == "v"
                        {
                            base_url.set_query(Some(&format!("v={}", value)));
                            return Ok(base_url);
                        }
                    }
                }

                // If no query param, check if path has /watch/ and extract ID
                let path = parsed_url.path();
                if path.starts_with("/watch/") {
                    let video_id = path.trim_start_matches("/watch/");
                    base_url.set_query(Some(&format!("v={}", video_id)));
                    return Ok(base_url);
                }

                // Handle youtu.be URLs - extract ID from path
                if parsed_url.host_str() == Some("youtu.be") {
                    let video_id = path.trim_start_matches('/');
                    base_url.set_query(Some(&format!("v={}", video_id)));
                    return Ok(base_url);
                }

                Err(url::ParseError::EmptyHost)
            }
            PlatformVariant::YouTubeShort => {
                let path = parsed_url.path();

                if path.contains("/shorts/") {
                    let video_id = path.split('/').next_back().unwrap();
                    base_url.set_path(&format!("/shorts/{}", video_id));
                    return Ok(base_url);
                }

                Err(url::ParseError::EmptyHost)
            }
            PlatformVariant::YouTubeClip => {
                let path = parsed_url.path();

                if path.contains("/clip/") {
                    let clip_id = path.split('/').next_back().unwrap();
                    base_url.set_path(&format!("/clip/{}", clip_id));
                    return Ok(base_url);
                }

                Err(url::ParseError::EmptyHost)
            }
            PlatformVariant::TwitchVOD => {
                let video_id = parsed_url.path().split('/').next_back().unwrap();
                base_url.join(&format!("/videos/{}", video_id))
            }
            PlatformVariant::TwitchClip => {
                let path = parsed_url.path();

                let clip_id = path.split('/').next_back().unwrap();

                base_url.join(clip_id)
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_platform_get_from_str() {
        assert_eq!(
            BasePlatform::get_from_str("youtube"),
            Some(BasePlatform::YouTube)
        );
        assert_eq!(
            BasePlatform::get_from_str("YouTube"),
            Some(BasePlatform::YouTube)
        );
        assert_eq!(
            BasePlatform::get_from_str("YOUTUBE"),
            Some(BasePlatform::YouTube)
        );

        assert_eq!(
            BasePlatform::get_from_str("twitch"),
            Some(BasePlatform::Twitch)
        );
        assert_eq!(
            BasePlatform::get_from_str("Twitch"),
            Some(BasePlatform::Twitch)
        );
        assert_eq!(
            BasePlatform::get_from_str("TWITCH"),
            Some(BasePlatform::Twitch)
        );

        assert_eq!(
            BasePlatform::get_from_str("discord"),
            Some(BasePlatform::Discord)
        );
        assert_eq!(
            BasePlatform::get_from_str("Discord"),
            Some(BasePlatform::Discord)
        );
        assert_eq!(
            BasePlatform::get_from_str("DISCORD"),
            Some(BasePlatform::Discord)
        );

        assert_eq!(BasePlatform::get_from_str("invalid"), None);
        assert_eq!(BasePlatform::get_from_str("youtube_invalid"), None);
        assert_eq!(BasePlatform::get_from_str(""), None);
    }

    #[test]
    fn test_platform_extract_timestamp() {
        assert_eq!(
            VideoPlatform::YouTube
                .extract_timestamp("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=456"),
            Some(456)
        );
        assert_eq!(
            VideoPlatform::Twitch
                .extract_timestamp("https://www.twitch.tv/videos/1234567890?t=06h10m54s"),
            Some(22254)
        );
        assert_eq!(
            VideoPlatform::Twitch
                .extract_timestamp("https://www.twitch.tv/videos/1234567890?t=32h24m31s"),
            Some(116671)
        );
        assert_eq!(
            VideoPlatform::Twitch
                .extract_timestamp("https://www.twitch.tv/videos/1234567890?t=10m54s"),
            Some(654)
        );
        assert_eq!(
            VideoPlatform::Twitch
                .extract_timestamp("https://www.twitch.tv/videos/1234567890?t=00h10m54s"),
            Some(654)
        );
        assert_eq!(
            VideoPlatform::Twitch
                .extract_timestamp("https://www.twitch.tv/videos/1234567890?t=54s"),
            Some(54)
        );
    }

    #[test]
    fn test_platform_timestamp_url() {
        assert_eq!(
            VideoPlatform::YouTube.timestamp_url("dQw4w9WgXcQ", &456.0),
            Url::parse("https://youtube.com/watch?v=dQw4w9WgXcQ&t=456").unwrap()
        );
        assert_eq!(
            VideoPlatform::Twitch.timestamp_url("1234567890", &22254.0),
            Url::parse("https://twitch.tv/videos/1234567890?t=06h10m54s").unwrap()
        );
        assert_eq!(
            VideoPlatform::Twitch.timestamp_url("1234567890", &116671.0),
            Url::parse("https://twitch.tv/videos/1234567890?t=32h24m31s").unwrap()
        );
        assert_eq!(
            VideoPlatform::Twitch.timestamp_url("1234567890", &654.0),
            Url::parse("https://twitch.tv/videos/1234567890?t=00h10m54s").unwrap()
        );
        assert_eq!(
            VideoPlatform::Twitch.timestamp_url("1234567890", &54.0),
            Url::parse("https://twitch.tv/videos/1234567890?t=00h00m54s").unwrap()
        );
    }
    #[test]
    fn test_youtube_video_variant_matches_url() {
        let valid_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&si=ESugKbhZOHe6PFbA",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&si=ESugKbhZOHe6PFbA&test=123",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&si=ESugKbhZOHe6PFbA&test=123&t=456",
            // "youtube.com/watch/1234567890", // TODO: Add support for this format
            "youtu.be/dQw4w9WgXcQ",
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
            PlatformVariant::from_url(
                "https://www.youtube.com/clip/UgkxFyeXQtfPRff43kUWbsAeuBND6Lb4ysEM"
            ),
            Some(PlatformVariant::YouTubeClip)
        );
        assert_eq!(
            PlatformVariant::from_url("https://www.twitch.tv/videos/1234567890"),
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

    #[test]
    fn test_youtube_video_standardized_url() {
        let test_cases = [
            // Standard watch URLs
            (
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "https://youtube.com/watch?v=dQw4w9WgXcQ",
            ),
            (
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ&si=ESugKbhZOHe6PFbA",
                "https://youtube.com/watch?v=dQw4w9WgXcQ",
            ),
            (
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=123",
                "https://youtube.com/watch?v=dQw4w9WgXcQ",
            ),
            (
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=123&test=123",
                "https://youtube.com/watch?v=dQw4w9WgXcQ",
            ),
            (
                "https://youtube.com/watch?v=dQw4w9WgXcQ",
                "https://youtube.com/watch?v=dQw4w9WgXcQ",
            ),
            // youtu.be URLs
            (
                "https://youtu.be/dQw4w9WgXcQ",
                "https://youtube.com/watch?v=dQw4w9WgXcQ",
            ),
            (
                "https://youtu.be/dQw4w9WgXcQ?si=ESugKbhZOHe6PFbA",
                "https://youtube.com/watch?v=dQw4w9WgXcQ",
            ),
            (
                "https://youtu.be/dQw4w9WgXcQ?t=123",
                "https://youtube.com/watch?v=dQw4w9WgXcQ",
            ),
            // /watch/ID format
            (
                "https://www.youtube.com/watch/dQw4w9WgXcQ",
                "https://youtube.com/watch?v=dQw4w9WgXcQ",
            ),
            (
                "https://youtube.com/watch/dQw4w9WgXcQ",
                "https://youtube.com/watch?v=dQw4w9WgXcQ",
            ),
        ];

        for (input_url, expected_url) in test_cases {
            let result = PlatformVariant::YouTubeVideo
                .standardized_url(input_url)
                .expect("Failed to sanitize URL");
            assert_eq!(
                result.as_str(),
                expected_url,
                "Failed to sanitize URL: {} -> expected: {}, got: {}",
                input_url,
                expected_url,
                result.as_str()
            );
        }
    }

    #[test]
    fn test_youtube_short_standardized_url() {
        let test_cases = [
            (
                "https://www.youtube.com/shorts/dQw4w9WgXcQ",
                "https://youtube.com/shorts/dQw4w9WgXcQ",
            ),
            (
                "https://www.youtube.com/shorts/dQw4w9WgXcQ?feature=shared&test=123",
                "https://youtube.com/shorts/dQw4w9WgXcQ",
            ),
            (
                "https://youtube.com/shorts/dQw4w9WgXcQ",
                "https://youtube.com/shorts/dQw4w9WgXcQ",
            ),
            (
                "https://youtube.com/shorts/dQw4w9WgXcQ?feature=shared",
                "https://youtube.com/shorts/dQw4w9WgXcQ",
            ),
            (
                "https://m.youtube.com/shorts/dQw4w9WgXcQ",
                "https://youtube.com/shorts/dQw4w9WgXcQ",
            ),
            (
                "https://m.youtube.com/shorts/dQw4w9WgXcQ?si=ESugKbhZOHe6PFbA",
                "https://youtube.com/shorts/dQw4w9WgXcQ",
            ),
        ];

        for (input_url, expected_url) in test_cases {
            let result = PlatformVariant::YouTubeShort
                .standardized_url(input_url)
                .expect("Failed to sanitize URL");
            assert_eq!(
                result.as_str(),
                expected_url,
                "Failed to standardize YouTube Short URL: {} -> expected: {}, got: {}",
                input_url,
                expected_url,
                result.as_str()
            );
        }
    }

    #[test]
    fn test_youtube_clip_standardized_url() {
        let test_cases = [
            (
                "https://www.youtube.com/clip/UgkxFyeXQtfPRff43kUWbsAeuBND6Lb4ysEM",
                "https://youtube.com/clip/UgkxFyeXQtfPRff43kUWbsAeuBND6Lb4ysEM",
            ),
            (
                "https://youtube.com/clip/UgkxFyeXQtfPRff43kUWbsAeuBND6Lb4ysEM?feature=shared&test=123",
                "https://youtube.com/clip/UgkxFyeXQtfPRff43kUWbsAeuBND6Lb4ysEM",
            ),
            (
                "https://youtube.com/clip/UgkxhANZ5PHqXaGMfg5qX-TDKX7Qn9UeDv5c?feature=shared",
                "https://youtube.com/clip/UgkxhANZ5PHqXaGMfg5qX-TDKX7Qn9UeDv5c",
            ),
            (
                "https://m.youtube.com/clip/UgkxFyeXQtfPRff43kUWbsAeuBND6Lb4ysEM",
                "https://youtube.com/clip/UgkxFyeXQtfPRff43kUWbsAeuBND6Lb4ysEM",
            ),
        ];

        for (input_url, expected_url) in test_cases {
            let result = PlatformVariant::YouTubeClip
                .standardized_url(input_url)
                .expect("Failed to sanitize URL");
            assert_eq!(
                result.as_str(),
                expected_url,
                "Failed to standardize YouTube Clip URL: {} -> expected: {}, got: {}",
                input_url,
                expected_url,
                result.as_str()
            );
        }
    }

    #[test]
    fn test_twitch_vod_standardized_url() {
        let test_cases = [
            (
                "https://www.twitch.tv/videos/1234567890",
                "https://twitch.tv/videos/1234567890",
            ),
            (
                "https://twitch.tv/videos/1234567890",
                "https://twitch.tv/videos/1234567890",
            ),
            (
                "https://www.twitch.tv/videos/3338399115?t=01h09m43s",
                "https://twitch.tv/videos/3338399115",
            ),
            (
                "https://m.twitch.tv/videos/3338399115?t=01h09m43s&test=123",
                "https://twitch.tv/videos/3338399115",
            ),
            (
                "https://m.twitch.tv/videos/3338399115",
                "https://twitch.tv/videos/3338399115",
            ),
        ];

        for (input_url, expected_url) in test_cases {
            let result = PlatformVariant::TwitchVOD
                .standardized_url(input_url)
                .expect("Failed to sanitize URL");
            assert_eq!(
                result.as_str(),
                expected_url,
                "Failed to standardize Twitch VOD URL: {} -> expected: {}, got: {}",
                input_url,
                expected_url,
                result.as_str()
            );
        }
    }

    #[test]
    fn test_twitch_clip_standardized_url() {
        let test_cases = [
            (
                "https://clips.twitch.tv/CleverClipName",
                "https://clips.twitch.tv/CleverClipName",
            ),
            (
                "https://clips.twitch.tv/CleverClipName?test=123",
                "https://clips.twitch.tv/CleverClipName",
            ),
            (
                "https://twitch.tv/broadcaster/clip/CleverClipName",
                "https://clips.twitch.tv/CleverClipName",
            ),
            (
                "https://clips.twitch.tv/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR",
                "https://clips.twitch.tv/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR",
            ),
            (
                "https://www.twitch.tv/brittt/clip/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR?filter=clips&range=all&sort=time",
                "https://clips.twitch.tv/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR",
            ),
            (
                "https://www.twitch.tv/brittt/clip/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR",
                "https://clips.twitch.tv/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR",
            ),
            (
                "https://m.twitch.tv/brittt/clip/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR",
                "https://clips.twitch.tv/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR",
            ),
        ];

        for (input_url, expected_url) in test_cases {
            let result = PlatformVariant::TwitchClip
                .standardized_url(input_url)
                .expect("Failed to sanitize URL");
            assert_eq!(
                result.as_str(),
                expected_url,
                "Failed to standardize Twitch Clip URL: {} -> expected: {}, got: {}",
                input_url,
                expected_url,
                result.as_str()
            );
        }
    }
    #[test]
    fn test_platform_variant_id_to_url() {
        let test_cases = [
            (
                "dQw4w9WgXcQ",
                PlatformVariant::YouTubeVideo,
                "https://youtube.com/watch?v=dQw4w9WgXcQ",
            ),
            (
                "short123",
                PlatformVariant::YouTubeShort,
                "https://youtube.com/shorts/short123",
            ),
            (
                "clip123",
                PlatformVariant::YouTubeClip,
                "https://youtube.com/clip/clip123",
            ),
            (
                "1489169293",
                PlatformVariant::TwitchVOD,
                "https://twitch.tv/videos/1489169293",
            ),
            (
                "IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR",
                PlatformVariant::TwitchClip,
                "https://clips.twitch.tv/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR",
            ),
        ];

        for (input_id, variant, expected_url) in test_cases {
            let result = variant.id_to_url(input_id);
            assert_eq!(
                result, expected_url,
                "Failed to convert ID to URL: {} -> expected: {}, got: {}",
                input_id, expected_url, result
            );
        }
    }

    #[test]
    fn test_platform_variant_timestamp_url() {
        let test_cases = [
            (
                "dQw4w9WgXcQ",
                VideoPlatform::YouTube,
                12345.0,
                Url::parse("https://youtube.com/watch?v=dQw4w9WgXcQ&t=12345").unwrap(),
            ),
            (
                "2489169293",
                VideoPlatform::Twitch,
                12345.0,
                Url::parse("https://twitch.tv/videos/2489169293?t=03h25m45s").unwrap(),
            ),
        ];

        for (input_id, variant, seconds, expected_url) in test_cases {
            let result = variant.timestamp_url(input_id, &seconds);
            assert_eq!(
                result, expected_url,
                "Failed to convert ID to URL: {} -> expected: {}, got: {}",
                input_id, expected_url, result
            );
        }
    }
}
