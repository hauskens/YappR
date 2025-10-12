#[cfg(feature = "database")]
use crate::entities::channels;
use crate::models::platforms::Platform;

pub trait Channel {
    fn platform(&self) -> Platform;
    fn channel_url(&self) -> String;
}

impl Channel for channels::Model {
    fn platform(&self) -> Platform {
        Platform::get_from_str(&self.platform_name)
            .unwrap_or_else(|| panic!("Channel has invalid platform name: {}", self.platform_name))
    }
    
    fn channel_url(&self) -> String {
        match self.platform() {
            Platform::YouTube => self.platform().base_url().join(&format!("/@{}", self.platform_ref)).unwrap().to_string(),
            Platform::Twitch => self.platform().base_url().join(&format!("/{}", self.platform_ref)).unwrap().to_string(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;
    use crate::entities::sea_orm_active_enums::Videotype;
    
    fn create_test_channel(id: i32, platform_name: &str, platform_channel_id: &str, platform_ref: &str) -> channels::Model {
        channels::Model {
            id,
            name: format!("Test Channel {}", id),
            broadcaster_id: 1,
            platform_ref: platform_ref.to_string(),
            main_video_type: Videotype::Clip,
            platform_channel_id: platform_channel_id.to_string(),
            source_channel_id: None,
            last_active: Some(Utc::now().naive_utc()),
            platform_name: platform_name.to_string(),
        }
    }
    
    #[test]
    fn test_youtube_channel_ext() {
        let channel = create_test_channel(1, "youtube", "testid", "UCTest123");
        
        assert_eq!(channel.platform(), Platform::YouTube);
        assert_eq!(channel.channel_url(), "https://youtube.com/@UCTest123".to_string());
    }
    
    #[test]
    fn test_twitch_channel_ext() {
        let channel = create_test_channel(2, "twitch", "testid", "teststreamer");
        
        assert_eq!(channel.platform(), Platform::Twitch);
        assert_eq!(channel.channel_url(), "https://twitch.tv/teststreamer".to_string());
    }
    
    #[test]
    #[should_panic(expected = "Channel has invalid platform name: invalid")]
    fn test_invalid_platform() {
        let channel = create_test_channel(3, "invalid", "testid", "testref");
        channel.platform();
    }
}