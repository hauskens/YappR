use chrono::{Duration, NaiveDateTime, NaiveTime, TimeZone, Utc};
use chrono_tz::Tz;
use regex::Regex;
use sea_orm::*;
use std::fs;
use std::path::PathBuf;

use crate::entities::prelude::*;
use crate::entities::sea_orm_active_enums::Channeleventtype;
use crate::entities::{channel_events, chatlog_imports, chatlogs};

#[derive(Debug, Clone)]
pub struct ParsedChatLog {
    pub channel_id: i32,
    pub timestamp: NaiveDateTime,
    pub username: String,
    pub message: String,
    pub import_id: Option<i32>,
}

#[derive(Debug, Clone)]
pub struct ParsedChannelEvent {
    pub channel_id: i32,
    pub timestamp: NaiveDateTime,
    pub event_type: Channeleventtype,
    pub username: Option<String>,
    pub raw_message: String,
    pub import_id: Option<i32>,
}

#[derive(Debug)]
pub enum ParsedItem {
    ChatLog(ParsedChatLog),
    ChannelEvent(ParsedChannelEvent),
}

pub struct ChatLogParser {
    message_regex: Regex,
    start_line_regex: Regex,
    timestamp_only_regex: Regex,
}

impl Default for ChatLogParser {
    fn default() -> Self {
        Self {
            message_regex: Regex::new(r"^\[(\d{2}:\d{2}:\d{2})\]\s+(.+): (.+)$").unwrap(),
            start_line_regex: Regex::new(
                r"# Start logging at (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})(?: (.+))?",
            )
            .unwrap(),
            timestamp_only_regex: Regex::new(r"^\[(\d{2}:\d{2}:\d{2})\] (.+)$").unwrap(),
        }
    }
}

impl ChatLogParser {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn parse_log_start_line(
        &self,
        line: &str,
    ) -> Result<(NaiveDateTime, String), Box<dyn std::error::Error>> {
        let caps = self
            .start_line_regex
            .captures(line)
            .ok_or("Invalid start line format")?;

        let date_str = caps.get(1).unwrap().as_str();
        let time_str = caps.get(2).unwrap().as_str();
        let timezone_str = caps.get(3).map(|m| m.as_str()).unwrap();

        let base_datetime = NaiveDateTime::parse_from_str(
            &format!("{} {}", date_str, time_str),
            "%Y-%m-%d %H:%M:%S",
        )?;

        Ok((base_datetime, timezone_str.to_string()))
    }

    pub fn extract_username(&self, full_username_str: &str) -> String {
        full_username_str
            .split_whitespace()
            .last()
            .unwrap_or("")
            .to_string()
    }

    pub fn parse_line(
        &self,
        line: &str,
        base_date: &mut NaiveDateTime,
        last_timestamp: &mut NaiveDateTime,
        channel_id: i32,
        timezone_str: &str,
        import_id: i32,
    ) -> Option<ParsedItem> {
        // Try to parse as chat message
        if let Some(caps) = self.message_regex.captures(line) {
            let time_part = caps.get(1).unwrap().as_str();
            let username = caps.get(2).unwrap().as_str();
            let message = caps.get(3).unwrap().as_str();

            match self.combine_with_base_date(time_part, base_date, last_timestamp, timezone_str) {
                Ok(full_timestamp) => {
                    return Some(ParsedItem::ChatLog(ParsedChatLog {
                        channel_id,
                        timestamp: full_timestamp,
                        username: self.extract_username(username),
                        message: message.to_string(),
                        import_id: Some(import_id),
                    }));
                }
                Err(e) => {
                    println!("    Error combining timestamp: {}", e);
                }
            }
        }

        // Try to parse as event
        if let Some(caps) = self.timestamp_only_regex.captures(line) {
            let time_part = caps.get(1).unwrap().as_str();
            let raw_message = caps.get(2).unwrap().as_str();

            if let Ok(full_timestamp) =
                self.combine_with_base_date(time_part, base_date, last_timestamp, timezone_str)
                && let Some((event_type, username)) =
                    self.parse_event_type_and_username(raw_message)
            {
                return Some(ParsedItem::ChannelEvent(ParsedChannelEvent {
                    channel_id,
                    timestamp: full_timestamp,
                    event_type,
                    username,
                    raw_message: raw_message.trim().to_string(),
                    import_id: Some(import_id),
                }));
            }
        }

        None
    }

    fn combine_with_base_date(
        &self,
        time_str: &str,
        base_date: &mut NaiveDateTime,
        last_timestamp: &mut NaiveDateTime,
        timezone_str: &str,
    ) -> Result<NaiveDateTime, Box<dyn std::error::Error>> {
        let current_time = NaiveTime::parse_from_str(time_str, "%H:%M:%S")?;
        let mut combined = base_date.date().and_time(current_time);

        if combined < *last_timestamp {
            combined += Duration::days(1);
            *base_date += Duration::days(1);
        }

        // Convert to server timezone using the provided timezone string
        let converted = self.convert_to_server_timezone(combined, timezone_str)?;
        *last_timestamp = converted; // Update with the converted timestamp

        Ok(converted)
    }

    fn convert_to_server_timezone(
        &self,
        naive_dt: NaiveDateTime,
        timezone_str: &str,
    ) -> Result<NaiveDateTime, Box<dyn std::error::Error>> {
        // Map common timezone abbreviations to IANA identifiers
        let iana_timezone = match timezone_str {
            "CEST" | "CET" => "Europe/Berlin",
            "EDT" | "EST" => "America/New_York",
            "CDT" | "CST" => "America/Chicago",
            "MDT" | "MST" => "America/Denver",
            "PDT" | "PST" => "America/Los_Angeles",
            "GMT" => "UTC",
            other => other, // Try to parse as-is
        };

        // Parse timezone string using mapped IANA identifier
        let source_tz: Tz = iana_timezone.parse().map_err(|_| {
            format!(
                "Invalid timezone: '{}' (mapped from '{}')",
                iana_timezone, timezone_str
            )
        })?;

        // Convert naive datetime to timezone-aware datetime in source timezone
        let source_dt = source_tz
            .from_local_datetime(&naive_dt)
            .single()
            .ok_or("Ambiguous or invalid datetime in source timezone")?;

        // Convert to UTC and return as naive (for database storage)
        let result = source_dt.with_timezone(&Utc).naive_utc();
        Ok(result)
    }

    fn parse_event_type_and_username(
        &self,
        raw_message: &str,
    ) -> Option<(Channeleventtype, Option<String>)> {
        let message = raw_message.trim();

        // Live events
        if message.contains(" is live!") {
            return Some((Channeleventtype::Live, None));
        }

        // Offline events
        if message.contains(" is now offline.") {
            return Some((Channeleventtype::Offline, None));
        }

        // Subscription events
        if message.contains(" subscribed with Prime") {
            let username = message
                .split(" subscribed with Prime")
                .next()?
                .trim()
                .to_string();
            return Some((Channeleventtype::Subscription, Some(username)));
        }

        if message.contains(" subscribed at Tier") {
            let username = message
                .split(" subscribed at Tier")
                .next()?
                .trim()
                .to_string();
            return Some((Channeleventtype::Subscription, Some(username)));
        }

        // Gift events
        if message.contains(" is gifting ") && message.contains(" Subs to ") {
            let username = message
                .split(" is gifting ")
                .nth(1)?
                .split(" Subs to")
                .next()?
                .trim()
                .to_string();
            return Some((Channeleventtype::Gift, Some(username)));
        }

        if message.contains(" gifted a Tier ")
            && message.contains(" sub to ")
            && message.ends_with("!")
        {
            let username = message.split(" gifted a Tier ").next()?.trim().to_string();
            return Some((Channeleventtype::Gift, Some(username)));
        }

        // Raid events
        if message.contains(" raiders from ") && message.contains(" have joined!") {
            let username_part = message
                .split(" raiders from ")
                .nth(1)?
                .split(" have joined!")
                .next()?
                .trim()
                .to_string();
            return Some((Channeleventtype::Raid, Some(username_part)));
        }

        None
    }
}

pub struct DuplicateChecker {
    margin_ms: i64,
}

impl DuplicateChecker {
    pub fn new(margin_ms: i64) -> Self {
        Self {
            margin_ms,
        }
    }


    pub async fn find_gaps_and_fill(
        &self,
        db: &DatabaseConnection,
        channel_id: i32,
        new_messages: &[ParsedChatLog],
    ) -> Result<Vec<ParsedChatLog>, DbErr> {
        if new_messages.is_empty() {
            return Ok(Vec::new());
        }

        let start_time = new_messages[0].timestamp - Duration::hours(12);
        let end_time = new_messages.last().unwrap().timestamp + Duration::hours(12);

        let existing_messages: Vec<chatlogs::Model> = Chatlogs::find()
            .filter(
                chatlogs::Column::ChannelId
                    .eq(channel_id)
                    .and(chatlogs::Column::Timestamp.between(start_time, end_time)),
            )
            .order_by_asc(chatlogs::Column::Timestamp)
            .all(db)
            .await?;

        let mut messages_to_insert = Vec::new();
        let margin_duration = Duration::milliseconds(self.margin_ms);

        for new_msg in new_messages {
            let mut is_duplicate = false;

            for existing_msg in &existing_messages {
                let time_diff = if new_msg.timestamp > existing_msg.timestamp {
                    new_msg.timestamp - existing_msg.timestamp
                } else {
                    existing_msg.timestamp - new_msg.timestamp
                };

                if time_diff <= margin_duration
                    && new_msg.username == existing_msg.username
                    && new_msg.message == existing_msg.message
                {
                    is_duplicate = true;
                    break;
                }
            }

            if !is_duplicate {
                messages_to_insert.push(new_msg.clone());
            }
        }

        Ok(messages_to_insert)
    }

    pub async fn find_event_gaps_and_fill(
        &self,
        db: &DatabaseConnection,
        channel_id: i32,
        new_events: &[ParsedChannelEvent],
    ) -> Result<Vec<ParsedChannelEvent>, DbErr> {
        if new_events.is_empty() {
            return Ok(Vec::new());
        }

        let start_time = new_events[0].timestamp - Duration::hours(12);
        let end_time = new_events.last().unwrap().timestamp + Duration::hours(12);

        let existing_events: Vec<channel_events::Model> = ChannelEvents::find()
            .filter(
                channel_events::Column::ChannelId
                    .eq(channel_id)
                    .and(channel_events::Column::Timestamp.between(start_time, end_time)),
            )
            .order_by_asc(channel_events::Column::Timestamp)
            .all(db)
            .await?;

        let mut events_to_insert = Vec::new();
        let margin_duration = Duration::milliseconds(self.margin_ms);

        for new_event in new_events {
            let mut is_duplicate = false;

            for existing_event in &existing_events {
                let time_diff = if new_event.timestamp > existing_event.timestamp {
                    new_event.timestamp - existing_event.timestamp
                } else {
                    existing_event.timestamp - new_event.timestamp
                };

                // Check for duplicates based on timestamp, event type, and raw message
                if time_diff <= margin_duration
                    && new_event.event_type == existing_event.event_type
                    && new_event.raw_message == *existing_event.raw_message.as_ref().unwrap_or(&String::new())
                {
                    is_duplicate = true;
                    break;
                }
            }

            if !is_duplicate {
                events_to_insert.push(new_event.clone());
            }
        }

        Ok(events_to_insert)
    }
}

pub async fn parse_chatlogs_command(
    db: &DatabaseConnection,
    path: PathBuf,
    channel_id: i32,
    imported_by: i32,
    timezone: Option<String>,
    events_only: bool,
    margin_ms: i64,
    dry_run: bool,
) -> Result<(), Box<dyn std::error::Error>> {
    let parser = ChatLogParser::new();
    let duplicate_checker = DuplicateChecker::new(margin_ms);

    if dry_run {
        println!("🔍 DRY RUN MODE - No data will be inserted into the database");
        println!("Configuration:");
        println!("  Channel ID: {}", channel_id);
        println!("  Imported by: {}", imported_by);
        println!("  Events only: {}", events_only);
        println!("  Margin (ms): {}", margin_ms);
        if let Some(ref tz) = timezone {
            println!("  Override timezone: {}", tz);
        }
        println!();
    }

    let log_files = if path.is_file() {
        vec![path]
    } else if path.is_dir() {
        fs::read_dir(&path)?
            .filter_map(|entry| entry.ok())
            .map(|entry| entry.path())
            .filter(|path| path.extension().is_some_and(|ext| ext == "log"))
            .collect()
    } else {
        return Err("Path is neither a file nor a directory".into());
    };

    let total_files = log_files.len();

    for log_file in log_files {
        println!("Processing log file: {:?}", log_file);

        let content = fs::read_to_string(&log_file)?;
        let lines: Vec<&str> = content.lines().collect();

        if lines.is_empty() || !lines[0].starts_with("# Start logging at") {
            eprintln!("Skipping file {:?}: Invalid format", log_file);
            continue;
        }

        let (mut base_date, detected_timezone) = parser.parse_log_start_line(lines[0])?;
        let final_timezone = timezone.clone().unwrap_or(detected_timezone.clone());
        let mut last_timestamp = base_date;

        if dry_run {
            println!("File: {:?}", log_file);
            println!("  Base date: {}", base_date);
            println!("  Detected timezone: {}", detected_timezone);
            println!("  Final timezone: {}", final_timezone);
        }

        let import_id = if !dry_run {
            let import_record = chatlog_imports::ActiveModel {
                id: NotSet,
                channel_id: Set(channel_id),
                imported_at: Set(Utc::now().naive_utc()),
                imported_by: Set(imported_by),
                timezone: Set(final_timezone.clone()),
            };
            let result = ChatlogImports::insert(import_record).exec(db).await?;
            result.last_insert_id
        } else {
            1
        };

        // Parse all items
        let mut chat_messages = Vec::new();
        let mut channel_events = Vec::new();

        for line in &lines[1..] {
            if let Some(parsed_item) = parser.parse_line(
                line,
                &mut base_date,
                &mut last_timestamp,
                channel_id,
                &final_timezone,
                import_id,
            ) {
                match parsed_item {
                    ParsedItem::ChatLog(chat_log) => {
                        if !events_only {
                            chat_messages.push(chat_log);
                        }
                    }
                    ParsedItem::ChannelEvent(event) => {
                        channel_events.push(event);
                    }
                }
            }
        }

        // Handle chat messages (duplicate detection and gap filling)
        if !events_only && !chat_messages.is_empty() {

            let messages_to_insert = duplicate_checker
                .find_gaps_and_fill(db, channel_id, &chat_messages)
                .await?;

            if dry_run {
                println!("  Would insert {} chat messages", messages_to_insert.len());
                if !messages_to_insert.is_empty() {
                    let first_msg = &messages_to_insert[0];
                    let last_msg = &messages_to_insert[messages_to_insert.len() - 1];
                    println!(
                        "  Time range: {} to {}",
                        first_msg.timestamp, last_msg.timestamp
                    );

                    // Show sample of messages
                    let sample_count = std::cmp::min(3, messages_to_insert.len());
                    println!("  Sample messages:");
                    for msg in messages_to_insert.iter().take(sample_count) {
                        println!(
                            "    [{}] {}: {}",
                            msg.timestamp.format("%H:%M:%S"),
                            msg.username,
                            msg.message
                        );
                    }
                }
            } else {
                // Insert chat messages
                let mut chat_models = Vec::new();
                for msg in messages_to_insert {
                    chat_models.push(chatlogs::ActiveModel {
                        id: NotSet,
                        channel_id: Set(msg.channel_id),
                        timestamp: Set(msg.timestamp),
                        username: Set(msg.username),
                        message: Set(msg.message),
                        external_user_account_id: NotSet,
                        import_id: Set(msg.import_id),
                    });
                }

                if !chat_models.is_empty() {
                    Chatlogs::insert_many(chat_models).exec(db).await?;
                }
            }
        }

        // Handle channel events (duplicate detection and gap filling)
        if !channel_events.is_empty() {
            let events_to_insert = if dry_run {
                // In dry run mode, simulate gap filling
                println!("  Would perform event gap filling analysis");
                channel_events // Just use all events for dry run
            } else {
                duplicate_checker.find_event_gaps_and_fill(db, channel_id, &channel_events).await?
            };

            if dry_run {
                println!("  Would insert {} channel events", events_to_insert.len());
                if !events_to_insert.is_empty() {
                    // Count events by type
                    let mut live_count = 0;
                    let mut offline_count = 0;
                    let mut subscription_count = 0;
                    let mut gift_count = 0;
                    let mut raid_count = 0;
                    let mut cheer_count = 0;
                    let mut follow_count = 0;

                    for event in &events_to_insert {
                        match event.event_type {
                            Channeleventtype::Live => live_count += 1,
                            Channeleventtype::Offline => offline_count += 1,
                            Channeleventtype::Subscription => subscription_count += 1,
                            Channeleventtype::Gift => gift_count += 1,
                            Channeleventtype::Raid => raid_count += 1,
                            Channeleventtype::Cheer => cheer_count += 1,
                            Channeleventtype::Follow => follow_count += 1,
                        }
                    }

                    let first_event = &events_to_insert[0];
                    let last_event = &events_to_insert[events_to_insert.len() - 1];
                    println!(
                        "  Time range: {} to {}",
                        first_event.timestamp, last_event.timestamp
                    );

                    println!("  Event breakdown:");
                    if live_count > 0 {
                        println!("    Live: {}", live_count);
                    }
                    if offline_count > 0 {
                        println!("    Offline: {}", offline_count);
                    }
                    if subscription_count > 0 {
                        println!("    Subscription: {}", subscription_count);
                    }
                    if gift_count > 0 {
                        println!("    Gift: {}", gift_count);
                    }
                    if raid_count > 0 {
                        println!("    Raid: {}", raid_count);
                    }
                    if cheer_count > 0 {
                        println!("    Cheer: {}", cheer_count);
                    }
                    if follow_count > 0 {
                        println!("    Follow: {}", follow_count);
                    }

                    // Show sample events
                    let sample_count = std::cmp::min(3, events_to_insert.len());
                    println!("  Sample events:");
                    for event in events_to_insert.iter().take(sample_count) {
                        println!(
                            "    [{}] {:?}: {}",
                            event.timestamp.format("%H:%M:%S"),
                            event.event_type,
                            event.raw_message
                        );
                    }
                }
            } else {
                // Insert channel events
                let mut event_models = Vec::new();
                for event in events_to_insert {
                    event_models.push(channel_events::ActiveModel {
                        id: NotSet,
                        channel_id: Set(event.channel_id),
                        timestamp: Set(event.timestamp),
                        raw_message: Set(Some(event.raw_message)),
                        event_type: Set(event.event_type),
                        username: Set(event.username),
                        user_id: NotSet,
                        import_id: Set(event.import_id),
                    });
                }

                if !event_models.is_empty() {
                    ChannelEvents::insert_many(event_models).exec(db).await?;
                }
            }
        } else if dry_run {
            println!("  No channel events found");
        }

        if dry_run {
            println!("  ✓ Dry run completed for file: {:?}", log_file);
        } else {
            println!("Successfully processed file: {:?}", log_file);
        }
    }

    if dry_run {
        println!("\n🎯 DRY RUN SUMMARY");
        println!("Total files processed: {}", total_files);
        println!("No data was inserted into the database.");
        println!("Run without --dry-run to perform the actual import.");
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::NaiveDate;

    #[test]
    fn test_parse_log_start_line() {
        let parser = ChatLogParser::new();

        // Test with timezone
        let line = "# Start logging at 2023-12-01 15:30:45 Eastern Standard Time";
        let result = parser.parse_log_start_line(line).unwrap();
        assert_eq!(
            result.0,
            NaiveDate::from_ymd_opt(2023, 12, 1)
                .unwrap()
                .and_hms_opt(15, 30, 45)
                .unwrap()
        );
        assert_eq!(result.1, "Eastern Standard Time");

        // Test with CEST
        let line = "# Start logging at 2024-04-28 00:04:03 CEST";
        let result = parser.parse_log_start_line(line).unwrap();
        assert_eq!(
            result.0,
            NaiveDate::from_ymd_opt(2024, 4, 28)
                .unwrap()
                .and_hms_opt(00, 4, 3)
                .unwrap()
        );
        assert_eq!(result.1, "CEST");
    }

    #[test]
    fn test_extract_username() {
        let parser = ChatLogParser::new();

        assert_eq!(parser.extract_username("john_doe"), "john_doe");
        assert_eq!(parser.extract_username("  john_doe  "), "john_doe");
        assert_eq!(parser.extract_username("prefix john_doe"), "john_doe");
        assert_eq!(
            parser.extract_username("multiple words john_doe"),
            "john_doe"
        );
    }

    #[test]
    fn test_parse_chat_message() {
        let parser = ChatLogParser::new();
        let mut base_date = NaiveDate::from_ymd_opt(2023, 12, 1)
            .unwrap()
            .and_hms_opt(15, 0, 0)
            .unwrap();
        let mut last_timestamp = base_date;

        let line = "[15:30:45] john_doe: Hello world!";
        let result = parser.parse_line(line, &mut base_date, &mut last_timestamp, 1, "UTC", 1);

        match result {
            Some(ParsedItem::ChatLog(chat_log)) => {
                assert_eq!(chat_log.channel_id, 1);
                assert_eq!(chat_log.username, "john_doe");
                assert_eq!(chat_log.message, "Hello world!");
                assert_eq!(
                    chat_log.timestamp,
                    NaiveDate::from_ymd_opt(2023, 12, 1)
                        .unwrap()
                        .and_hms_opt(15, 30, 45)
                        .unwrap()
                );
            }
            _ => panic!("Expected ChatLog"),
        }
    }

    #[test]
    fn test_parse_subscription_event() {
        let parser = ChatLogParser::new();
        let mut base_date = NaiveDate::from_ymd_opt(2023, 12, 1)
            .unwrap()
            .and_hms_opt(15, 0, 0)
            .unwrap();
        let mut last_timestamp = base_date;

        let line = "[15:30:45] alice_viewer subscribed with Prime.";
        let result = parser.parse_line(line, &mut base_date, &mut last_timestamp, 1, "UTC", 1);

        match result {
            Some(ParsedItem::ChannelEvent(event)) => {
                assert_eq!(event.channel_id, 1);
                assert_eq!(event.event_type, Channeleventtype::Subscription);
                assert_eq!(event.username, Some("alice_viewer".to_string()));
                assert_eq!(event.raw_message, "alice_viewer subscribed with Prime.");
            }
            _ => panic!("Expected ChannelEvent"),
        }
    }

    #[test]
    fn test_parse_raid_event() {
        let parser = ChatLogParser::new();
        let mut base_date = NaiveDate::from_ymd_opt(2023, 12, 1)
            .unwrap()
            .and_hms_opt(15, 0, 0)
            .unwrap();
        let mut last_timestamp = base_date;

        let line = "[15:30:45] 50 raiders from cool_streamer have joined!";
        let result = parser.parse_line(line, &mut base_date, &mut last_timestamp, 1, "UTC", 1);

        match result {
            Some(ParsedItem::ChannelEvent(event)) => {
                assert_eq!(event.event_type, Channeleventtype::Raid);
                assert_eq!(event.username, Some("cool_streamer".to_string()));
            }
            _ => panic!("Expected ChannelEvent"),
        }
    }

    #[test]
    fn test_parse_live_event() {
        let parser = ChatLogParser::new();
        let mut base_date = NaiveDate::from_ymd_opt(2023, 12, 1)
            .unwrap()
            .and_hms_opt(15, 0, 0)
            .unwrap();
        let mut last_timestamp = base_date;

        let line = "[15:30:45] streamer_name is live!";
        let result = parser.parse_line(line, &mut base_date, &mut last_timestamp, 1, "UTC", 1);

        match result {
            Some(ParsedItem::ChannelEvent(event)) => {
                assert_eq!(event.event_type, Channeleventtype::Live);
                assert_eq!(event.username, None); // Live events don't extract username
            }
            _ => panic!("Expected ChannelEvent"),
        }
    }

    #[test]
    fn test_parse_gift_event() {
        let parser = ChatLogParser::new();
        let mut base_date = NaiveDate::from_ymd_opt(2023, 12, 1)
            .unwrap()
            .and_hms_opt(15, 0, 0)
            .unwrap();
        let mut last_timestamp = base_date;

        let line = "[15:30:45] generous_user gifted a Tier 1 sub to lucky_viewer!";
        let result = parser.parse_line(line, &mut base_date, &mut last_timestamp, 1, "UTC", 1);

        match result {
            Some(ParsedItem::ChannelEvent(event)) => {
                assert_eq!(event.event_type, Channeleventtype::Gift);
                assert_eq!(event.username, Some("generous_user".to_string()));
            }
            _ => panic!("Expected ChannelEvent"),
        }
    }

    #[test]
    fn test_day_rollover() {
        let parser = ChatLogParser::new();
        let mut base_date = NaiveDate::from_ymd_opt(2023, 12, 1)
            .unwrap()
            .and_hms_opt(23, 0, 0)
            .unwrap();
        let mut last_timestamp = NaiveDate::from_ymd_opt(2023, 12, 1)
            .unwrap()
            .and_hms_opt(23, 30, 0)
            .unwrap();

        // Parse a message that's earlier in the day than the last timestamp - should trigger day rollover
        let line = "[01:00:00] user: Good morning!";
        let result = parser.parse_line(line, &mut base_date, &mut last_timestamp, 1, "UTC", 1);

        match result {
            Some(ParsedItem::ChatLog(chat_log)) => {
                // Should be December 2nd now due to rollover
                assert_eq!(
                    chat_log.timestamp,
                    NaiveDate::from_ymd_opt(2023, 12, 2)
                        .unwrap()
                        .and_hms_opt(1, 0, 0)
                        .unwrap()
                );
            }
            _ => panic!("Expected ChatLog"),
        }
    }

    #[test]
    fn test_invalid_lines() {
        let parser = ChatLogParser::new();
        let mut base_date = NaiveDate::from_ymd_opt(2023, 12, 1)
            .unwrap()
            .and_hms_opt(15, 0, 0)
            .unwrap();
        let mut last_timestamp = base_date;

        // Invalid chat message format
        let line = "Invalid line format";
        let result = parser.parse_line(line, &mut base_date, &mut last_timestamp, 1, "UTC", 1);
        assert!(result.is_none());

        // Timestamp without message
        let line = "[15:30:45]";
        let result = parser.parse_line(line, &mut base_date, &mut last_timestamp, 1, "UTC", 1);
        assert!(result.is_none());

        // Empty line
        let line = "";
        let result = parser.parse_line(line, &mut base_date, &mut last_timestamp, 1, "UTC", 1);
        assert!(result.is_none());
    }


    #[test]
    fn test_parse_multiple_message_types() {
        let parser = ChatLogParser::new();
        let mut base_date = NaiveDate::from_ymd_opt(2023, 12, 1)
            .unwrap()
            .and_hms_opt(15, 0, 0)
            .unwrap();
        let mut last_timestamp = base_date;

        let lines = vec![
            "[15:30:45] user1: Hello everyone!",
            "[15:31:00] viewer2 subscribed at Tier 1.",
            "[15:31:15] user3: Welcome viewer2!",
            "[15:31:30] 25 raiders from other_streamer have joined!",
            "[15:31:45] streamer is live!",
        ];

        let mut chat_count = 0;
        let mut event_count = 0;

        for line in lines {
            let result =
                parser.parse_line(line, &mut base_date, &mut last_timestamp, 1, "UTC", 1);
            match result {
                Some(ParsedItem::ChatLog(_)) => chat_count += 1,
                Some(ParsedItem::ChannelEvent(_)) => event_count += 1,
                None => {}
            }
        }

        assert_eq!(chat_count, 2); // Two chat messages
        assert_eq!(event_count, 3); // Three events (sub, raid, live)
    }
    #[test]
    fn test_timezone_conversion() {
        let parser = ChatLogParser::new();
        let naive_dt = NaiveDate::from_ymd_opt(2023, 12, 1)
            .unwrap()
            .and_hms_opt(15, 30, 45)
            .unwrap();

        // Test valid IANA timezone
        let result = parser.convert_to_server_timezone(naive_dt, "America/New_York");
        assert!(result.is_ok());

        // Test UTC
        let result = parser.convert_to_server_timezone(naive_dt, "UTC");
        assert!(result.is_ok());
        assert_eq!(result.unwrap(), naive_dt); // UTC should be unchanged

        // Test invalid timezone - should fail
        let result = parser.convert_to_server_timezone(naive_dt, "Invalid/Timezone");
        assert!(result.is_err());

        // Test another valid timezone
        let result = parser.convert_to_server_timezone(naive_dt, "Europe/Berlin");
        assert!(result.is_ok());
    }

    #[test]
    fn test_edge_case_usernames() {
        let parser = ChatLogParser::new();
        let mut base_date = NaiveDate::from_ymd_opt(2023, 12, 1)
            .unwrap()
            .and_hms_opt(15, 0, 0)
            .unwrap();
        let mut last_timestamp = base_date;

        // Username with underscores and numbers
        let line = "[15:30:45] user_123_test: Message with special chars!@#";
        let result = parser.parse_line(line, &mut base_date, &mut last_timestamp, 1, "UTC", 1);

        match result {
            Some(ParsedItem::ChatLog(chat_log)) => {
                assert_eq!(chat_log.username, "user_123_test");
                assert_eq!(chat_log.message, "Message with special chars!@#");
            }
            _ => panic!("Expected ChatLog"),
        }
    }

    #[test]
    fn test_subscription_tier_parsing() {
        let parser = ChatLogParser::new();
        let mut base_date = NaiveDate::from_ymd_opt(2023, 12, 1)
            .unwrap()
            .and_hms_opt(15, 0, 0)
            .unwrap();
        let mut last_timestamp = base_date;

        let line =
            "[15:30:45] premium_user subscribed at Tier 3. They've subscribed for 24 months!";
        let result = parser.parse_line(line, &mut base_date, &mut last_timestamp, 1, "UTC", 1);

        match result {
            Some(ParsedItem::ChannelEvent(event)) => {
                assert_eq!(event.event_type, Channeleventtype::Subscription);
                assert_eq!(event.username, Some("premium_user".to_string()));
            }
            _ => panic!("Expected ChannelEvent"),
        }
    }
}
