#[cfg(feature = "database")]
use crate::entities::{channels, video};
#[cfg(feature = "database")]
use sea_orm::{DatabaseConnection, EntityTrait, QueryFilter, ColumnTrait, DbErr};
use crate::models::platforms::VideoPlatform;
use async_trait::async_trait;

pub trait Channel {
    fn platform(&self) -> VideoPlatform;
    fn channel_url(&self) -> String;
}

/// Extension trait for channel database operations
/// This allows you to call methods like `channel.get_videos(db).await?`
#[cfg(feature = "database")]
#[async_trait]
pub trait ChannelExt {
    /// Get all videos for this channel
    async fn get_videos(&self, db: &DatabaseConnection) -> Result<Vec<video::Model>, DbErr>;

    /// Get active videos only for this channel
    async fn get_active_videos(&self, db: &DatabaseConnection) -> Result<Vec<video::Model>, DbErr>;

    /// Get videos by type (e.g., Clip, Vod, Stream)
    async fn get_videos_by_type(&self, db: &DatabaseConnection, video_type: crate::entities::sea_orm_active_enums::Videotype) -> Result<Vec<video::Model>, DbErr>;

    /// Get the most recent videos (limited by count)
    async fn get_recent_videos(&self, db: &DatabaseConnection, limit: u64) -> Result<Vec<video::Model>, DbErr>;
}

impl Channel for channels::Model {
    fn platform(&self) -> VideoPlatform {
        VideoPlatform::get_from_str(&self.platform_name)
            .unwrap_or_else(|| panic!("Channel has invalid platform name: {}", self.platform_name))
    }
    
    fn channel_url(&self) -> String {
        match self.platform() {
            VideoPlatform::YouTube => self.platform().base_url().join(&format!("/@{}", self.platform_ref)).unwrap().to_string(),
            VideoPlatform::Twitch => self.platform().base_url().join(&format!("/{}", self.platform_ref)).unwrap().to_string(),
        }
    }
}

#[cfg(feature = "database")]
#[async_trait]
impl ChannelExt for channels::Model {
    async fn get_videos(&self, db: &DatabaseConnection) -> Result<Vec<video::Model>, DbErr> {
        use crate::entities::prelude::*;

        Video::find()
            .filter(video::Column::ChannelId.eq(self.id))
            .all(db)
            .await
    }

    async fn get_active_videos(&self, db: &DatabaseConnection) -> Result<Vec<video::Model>, DbErr> {
        use crate::entities::prelude::*;

        Video::find()
            .filter(video::Column::ChannelId.eq(self.id))
            .filter(video::Column::Active.eq(true))
            .all(db)
            .await
    }

    async fn get_videos_by_type(&self, db: &DatabaseConnection, video_type: crate::entities::sea_orm_active_enums::Videotype) -> Result<Vec<video::Model>, DbErr> {
        use crate::entities::prelude::*;

        Video::find()
            .filter(video::Column::ChannelId.eq(self.id))
            .filter(video::Column::VideoType.eq(video_type))
            .all(db)
            .await
    }

    async fn get_recent_videos(&self, db: &DatabaseConnection, limit: u64) -> Result<Vec<video::Model>, DbErr> {
        use crate::entities::prelude::*;
        use sea_orm::{QueryOrder, QuerySelect};

        Video::find()
            .filter(video::Column::ChannelId.eq(self.id))
            .order_by_desc(video::Column::Uploaded)
            .limit(limit)
            .all(db)
            .await
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
        
        assert_eq!(channel.platform(), VideoPlatform::YouTube);
        assert_eq!(channel.channel_url(), "https://youtube.com/@UCTest123".to_string());
    }
    
    #[test]
    fn test_twitch_channel_ext() {
        let channel = create_test_channel(2, "twitch", "testid", "teststreamer");
        
        assert_eq!(channel.platform(), VideoPlatform::Twitch);
        assert_eq!(channel.channel_url(), "https://twitch.tv/teststreamer".to_string());
    }
    
    #[test]
    #[should_panic(expected = "Channel has invalid platform name: invalid")]
    fn test_invalid_platform() {
        let channel = create_test_channel(3, "invalid", "testid", "testref");
        channel.platform();
    }
}