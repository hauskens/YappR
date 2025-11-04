use regex::Regex;
use std::time::Duration;
use tracing::{debug, instrument, warn};

/// Parse a duration string in the format "XhYmZs" into a Duration
/// For example: "1h30m" or "45m" or "1h2m3s" -> Duration in seconds
#[instrument(level = "debug")]
pub fn parse_duration(input: &str) -> Result<Duration, Box<dyn std::error::Error>> {
    debug!(input = %input, "Parsing duration string");

    let re = Regex::new(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?")?;
    let caps = match re.captures(input) {
        Some(caps) => caps,
        None => {
            warn!(input = %input, "Invalid duration format");
            return Err("Invalid format".into());
        }
    };

    let hours: u64 = caps.get(1).map_or(0, |m| m.as_str().parse().unwrap_or(0));
    let minutes: u64 = caps.get(2).map_or(0, |m| m.as_str().parse().unwrap_or(0));
    let seconds: u64 = caps.get(3).map_or(0, |m| m.as_str().parse().unwrap_or(0));

    let duration = Duration::from_secs(hours * 3600 + minutes * 60 + seconds);
    debug!(
        input = %input,
        hours = hours,
        minutes = minutes,
        seconds = seconds,
        total_seconds = duration.as_secs(),
        "Successfully parsed duration"
    );

    Ok(duration)
}

/// Format a duration in seconds as "XhYmZs"
/// For example: 3661 -> "1h1m1s"
#[instrument(level = "debug")]
pub fn format_timestamp_hms(seconds: &u64) -> String {
    let hours = seconds / 3600;
    let minutes = (seconds % 3600) / 60;
    let secs = seconds % 60;

    let formatted = format!("{:02}h{:02}m{:02}s", hours, minutes, secs);
    debug!(
        input_seconds = seconds,
        hours = hours,
        minutes = minutes,
        seconds = secs,
        formatted = %formatted,
        "Formatted timestamp"
    );

    formatted
}
