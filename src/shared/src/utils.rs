use std::time::Duration;
use regex::Regex;

/// Parse a duration string in the format "XhYmZs" into a Duration
/// For example: "1h30m" or "45m" or "1h2m3s" -> Duration in seconds
pub fn parse_duration(input: &str) -> Result<Duration, Box<dyn std::error::Error>> {
    let re = Regex::new(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?")?;
    let caps = re.captures(input).ok_or("Invalid format")?;

    let hours: u64 = caps.get(1).map_or(0, |m| m.as_str().parse().unwrap_or(0));
    let minutes: u64 = caps.get(2).map_or(0, |m| m.as_str().parse().unwrap_or(0));
    let seconds: u64 = caps.get(3).map_or(0, |m| m.as_str().parse().unwrap_or(0));

    Ok(Duration::from_secs(hours * 3600 + minutes * 60 + seconds))
}

/// Format a duration in seconds as "XhYmZs"
/// For example: 3661 -> "1h1m1s"
pub fn format_timestamp_hms(seconds: u64) -> String {
    let hours = seconds / 3600;
    let minutes = (seconds % 3600) / 60;
    let secs = seconds % 60;

    format!("{:02}h{:02}m{:02}s", hours, minutes, secs)
}