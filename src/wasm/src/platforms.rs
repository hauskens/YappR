

#[derive(Clone, PartialEq)]
pub enum PlatformType {
    YouTube,
    Twitch,
}

impl PlatformType {
    pub fn from_string(platform: &str) -> Option<Self> {
        match platform.to_lowercase().as_str() {
            "youtube" => Some(PlatformType::YouTube),
            "twitch" => Some(PlatformType::Twitch),
            _ => None,
        }
    }
}

pub fn get_url_with_timestamp(platform_type: &PlatformType, platform_ref: &str, seconds_offset: f64) -> String {
    let base_url = match platform_type {
        PlatformType::YouTube => format!("https://www.youtube.com/watch?v={}", platform_ref),
        PlatformType::Twitch => format!("https://www.twitch.tv/videos/{}", platform_ref),
    };

    let seconds_offset = seconds_offset.max(0.0) as i32;

    match platform_type {
        PlatformType::YouTube => {
            // YouTube uses t=123s format (seconds)
            format!("{}&t={}s", base_url, seconds_offset)
        },
        PlatformType::Twitch => {
            // Twitch uses t=01h23m45s format
            let hours = seconds_offset / 3600;
            let minutes = (seconds_offset % 3600) / 60;
            let seconds = seconds_offset % 60;

            let timestamp = if hours > 0 {
                format!("{:02}h{:02}m{:02}s", hours, minutes, seconds)
            } else if minutes > 0 {
                format!("{:02}m{:02}s", minutes, seconds)
            } else {
                format!("{:02}s", seconds)
            };

            format!("{}?t={}", base_url, timestamp)
        }
    }
}