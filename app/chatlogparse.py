import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from app.models import db
from app.models import ChatLog, ChannelEvent, ChatLogImport
from app.models.enums import ChannelEventType
from typing import Optional, Union, List
from pathlib import Path
from app.logger import logger
from app.models.config import config
from sqlalchemy import and_, func

SERVER_TZ = ZoneInfo(config.timezone)

MESSAGE_REGEX = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s+(.+): (.+)$")

START_LINE_REGEX = re.compile(
    r"# Start logging at (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})(?: (.+))?")

TIMESTAMP_ONLY_REGEX = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\] (.+)$")


def convert_log_timezone_to_server(log_datetime: datetime, log_timezone_str: str) -> datetime:
    """
    Convert a datetime from the log's timezone to the server's timezone.
    
    Args:
        log_datetime: Naive datetime from the log
        log_timezone_str: Timezone string from the log (e.g., "Eastern Daylight Time", "UTC")
    
    Returns:
        Naive datetime converted to server timezone for database storage
    """
    try:
        # Map common timezone names to proper IANA timezone identifiers
        timezone_mapping = {
            'Eastern Daylight Time': 'US/Eastern',
            'Eastern Standard Time': 'US/Eastern', 
            'Central Daylight Time': 'US/Central',
            'Central Standard Time': 'US/Central',
            'Mountain Daylight Time': 'US/Mountain', 
            'Mountain Standard Time': 'US/Mountain',
            'Pacific Daylight Time': 'US/Pacific',
            'Pacific Standard Time': 'US/Pacific',
            'CEST': 'Europe/Berlin',  # Central European Summer Time
            'CET': 'Europe/Berlin',   # Central European Time
            'UTC': 'UTC',
            'GMT': 'UTC'
        }
        
        # Get proper IANA timezone name
        iana_timezone = timezone_mapping.get(log_timezone_str, log_timezone_str)
        
        try:
            log_tz = ZoneInfo(iana_timezone)
        except Exception:
            log_tz = ZoneInfo('UTC')
        
        # Convert the naive datetime to timezone-aware in the log's timezone
        log_aware = log_datetime.replace(tzinfo=log_tz)
        
        # Convert to server timezone
        server_aware = log_aware.astimezone(SERVER_TZ)
        
        # Return as naive datetime for database storage
        return server_aware.replace(tzinfo=None)
        
    except Exception as e:
        # Fallback: return original datetime
        return log_datetime


class ChatLogParser:
    def __init__(self, base_date: datetime, channel_id: int, log_timezone: str = "UTC"):
        self.base_date = base_date
        self.last_timestamp = base_date
        self.channel_id = channel_id
        self.log_timezone = log_timezone

    def extract_username(self, full_username_str: str) -> str:
        # username is the last "word" before colon, split by spaces
        # strip whitespace just in case
        return full_username_str.strip().split(" ")[-1]

    def parse_line(self, line: str) -> Optional[Union[ChatLog, ChannelEvent]]:
        chat_match = MESSAGE_REGEX.match(line)
        if chat_match:
            time_part, username, message = chat_match.groups()
            try:
                full_timestamp = self._combine_with_base_date(time_part)
                return ChatLog(
                    channel_id=self.channel_id,
                    timestamp=full_timestamp,
                    username=self.extract_username(username),
                    message=message,
                )
            except Exception as e:
                logger.warning(
                    f"Failed to parse chat message timestamp: {line.strip()} | {e}")
                return None

        event_match = TIMESTAMP_ONLY_REGEX.match(line)
        if event_match:
            time_part, raw_message = event_match.groups()
            try:
                full_timestamp = self._combine_with_base_date(time_part)
                event_type, username = self._parse_event_type_and_username(raw_message)
                
                if event_type:
                    return ChannelEvent(
                        channel_id=self.channel_id,
                        timestamp=full_timestamp,
                        event_type=event_type,
                        username=username,
                        raw_message=raw_message.strip(),
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to parse event timestamp: {line.strip()} | {e}")
                return None

        logger.info(f"Ignored or unparseable line: {line.strip()}")
        return None

    def _combine_with_base_date(self, time_str: str) -> datetime:
        current_time = datetime.strptime(time_str, "%H:%M:%S").time()
        combined = datetime.combine(self.base_date.date(), current_time)

        if combined < self.last_timestamp:
            combined += timedelta(days=1)
            self.base_date += timedelta(days=1)

        # Convert from log timezone to server timezone
        combined_server_tz = convert_log_timezone_to_server(combined, self.log_timezone)
        
        self.last_timestamp = combined
        return combined_server_tz

    def _parse_event_type_and_username(self, raw_message: str) -> tuple[ChannelEventType | None, str | None]:
        """Parse event type and extract username from raw message."""
        message = raw_message.strip()
        
        # Live events: "username is live!" - no username needed (it's the streamer)
        if " is live!" in message:
            return ChannelEventType.Live, None
        
        # Offline events: "username is now offline." - no username needed (it's the streamer)
        if " is now offline." in message:
            return ChannelEventType.Offline, None
        
        # Subscription events: "username subscribed with Prime."
        if " subscribed with Prime" in message:
            username = message.split(" subscribed with Prime")[0].strip()
            return ChannelEventType.Subscription, username
        
        # Subscription events: "username subscribed at Tier 1..."
        if " subscribed at Tier" in message:
            username = message.split(" subscribed at Tier")[0].strip()
            return ChannelEventType.Subscription, username
        
        # Individual gift events: "username is gifting 1 Tier 1 Subs to"
        if " is gifting " in message and " Subs to " in message:
            username = message.split(" is gifting ")[1].split(" Subs to")[0].strip()
            return ChannelEventType.Gift, username

        # Individual gift events: "username gifted a Tier 1 sub to username!"
        if " gifted a Tier " in message and " sub to " in message and message.endswith("!"):
            username = message.split(" gifted a Tier ")[0].strip()
            return ChannelEventType.Gift, username
        
        # Skip grouped gift messages: "username is gifting 5 Tier 1 Subs to username's community!"
        if " is gifting " in message and " Subs to " in message:
            return None, None
        
        # Raid events: "4 raiders from username have joined!"
        if " raiders from " in message and " have joined!" in message:
            username_part = message.split(" raiders from ")[1].split(" have joined!")[0].strip()
            return ChannelEventType.Raid, username_part
        
        return None, None


def parse_log_start_line(line: str) -> tuple[datetime, str]:
    """
    Parse the start line and extract datetime and timezone.
    Returns tuple of (datetime, timezone_string)
    """
    match = START_LINE_REGEX.match(line)
    if not match:
        raise ValueError(f"Invalid start line: {line}")
    date_str, time_str, timezone_str = match.groups()
    base_datetime = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
    
    # Default to UTC if no timezone specified
    timezone_name = timezone_str or "UTC"
    
    return base_datetime, timezone_name


def check_for_duplicate_import(channel_id: int, first_messages: List[ChatLog], timezone_str: str) -> bool:
    """
    Check if these messages already exist by comparing exactly 10 consecutive messages
    within a 24-hour window around the timestamp range.
    Returns True if duplicates are found (regardless of import source), False otherwise.
    """
    if not first_messages or len(first_messages) < 10:
        logger.info(f"Not enough messages for duplicate detection: {len(first_messages)} (need 10)")
        return False
    
    # Use exactly the first 10 messages for comparison
    sample_messages = first_messages[:10]
    
    # Get the timestamp range of our sample messages
    start_time = sample_messages[0].timestamp
    end_time = sample_messages[-1].timestamp
    
    # Create 24-hour buffer around our sample timeframe
    search_start = start_time - timedelta(hours=24)
    search_end = end_time + timedelta(hours=24)
    
    logger.info(f"Checking for duplicates using 10-message sequence in timeframe {search_start} to {search_end}")
    
    # Get existing messages in the extended timeframe
    existing_messages = db.session.query(ChatLog).filter(
        and_(
            ChatLog.channel_id == channel_id,
            ChatLog.timestamp >= search_start,
            ChatLog.timestamp <= search_end
        )
    ).order_by(ChatLog.timestamp).all()
    
    if len(existing_messages) < 10:
        logger.info(f"Not enough existing messages for comparison: {len(existing_messages)}")
        return False
    
    # Convert sample messages to comparison tuples (username, message)
    sample_tuples = [(msg.username, msg.message) for msg in sample_messages]
    
    # Sliding window search through existing messages for exactly 10 consecutive matches
    for i in range(len(existing_messages) - 9):  # -9 because we need 10 consecutive
        window_tuples = [(existing_messages[i + j].username, existing_messages[i + j].message) 
                        for j in range(10)]
        
        if sample_tuples == window_tuples:
            # Found matching sequence of exactly 10 messages - determine the source
            matching_messages = existing_messages[i:i + 10]
            import_source = "bot/live collection"
            
            # Check if any message has an import_id to identify user import
            for msg in matching_messages:
                if msg.import_id:
                    import_record = db.session.query(ChatLogImport).filter_by(id=msg.import_id).first()
                    if import_record:
                        import_source = f"user import {import_record.id} by user {import_record.imported_by} at {import_record.imported_at}"
                    break
            
            logger.warning(f"Found duplicate 10-message sequence from {import_source}")
            return True
    
    logger.info("No duplicate 10-message sequences found")
    return False


def create_import_record(channel_id: int, imported_by: int, timezone_str: str) -> ChatLogImport:
    """Create a new ChatLogImport record."""
    import_record = ChatLogImport(
        channel_id=channel_id,
        imported_at=datetime.now(timezone.utc),
        imported_by=imported_by,
        timezone=timezone_str
    )
    db.session.add(import_record)
    db.session.flush()  # Get the ID without committing
    return import_record


def parse_logs(folder_path: str, channel_id: int, imported_by: int, timezone_str: str = "UTC"):
    log_folder = Path(folder_path)
    logger.info(f"Parsing logs from {log_folder}")
    for log_file in log_folder.glob("*.log"):
        logger.info(f"Parsing {log_file}")
        parse_log(log_file.as_posix(), channel_id, imported_by, timezone_str)


def parse_log(log_path: str, channel_id: int, imported_by: int | None = None, timezone_str: str | None = None, events_only: bool = False):
    """
    Parse a chat log file and import it with duplicate detection.
    
    Args:
        log_path: Path to the log file
        channel_id: Channel ID to associate messages with
        imported_by: User ID who is importing (None for legacy/bot imports)
        timezone_str: Override timezone string (None to auto-detect from file)
        events_only: If True, only import events and skip chat messages (bypasses all duplication checks)
    """
    logger.info(f"Starting parse_log with events_only={events_only}, channel_id={channel_id}")
    with Path(log_path).open("r", encoding="utf-8") as f:
        lines = f.readlines()
    if not lines or not lines[0].startswith("# Start logging at"):
        raise ValueError(
            "Log must start with '# Start logging at YYYY-MM-DD HH:MM:SS ...'")
    
    base_date, detected_timezone = parse_log_start_line(lines[0])
    # Use provided timezone or fall back to detected timezone
    final_timezone = timezone_str or detected_timezone
    parser = ChatLogParser(base_date, channel_id, final_timezone)

    # First pass: parse items (collect chat messages for duplicate detection only if not events-only)
    first_chat_messages: list[ChatLog] = []
    all_parsed_items: list[ChatLog | ChannelEvent] = []
    
    logger.info(f"Parsing {len(lines)-1} lines from {log_path} (events_only={events_only})")
    
    for line in lines[1:]:
        result = parser.parse_line(line)
        if result:
            # In events-only mode, only add ChannelEvent items and skip chat message collection
            if events_only:
                if isinstance(result, ChannelEvent):
                    all_parsed_items.append(result)
                # Explicitly skip ChatLog items and don't add to first_chat_messages
            else:
                all_parsed_items.append(result)
                if isinstance(result, ChatLog) and len(first_chat_messages) < 10:
                    first_chat_messages.append(result)
    
    # Handle import record creation based on mode
    import_record = None
    if imported_by:
        if events_only:
            # For events-only imports, completely skip duplication check and create import record
            logger.info(f"Events-only mode enabled - bypassing all duplication checks for channel {channel_id}")
            import_record = create_import_record(channel_id, imported_by, final_timezone)
            logger.info(f"Created import record {import_record.id} for events-only import with timezone {final_timezone} (duplication check skipped)")
        elif first_chat_messages:
            # For chat imports, check for duplicates first
            logger.info(f"Running duplication check for {len(first_chat_messages)} chat messages")
            has_duplicates = check_for_duplicate_import(channel_id, first_chat_messages, final_timezone)
            if has_duplicates:
                raise ValueError(f"This log appears to contain duplicate messages that already exist in the database (from bot collection or previous import)")
            
            # Create import record
            import_record = create_import_record(channel_id, imported_by, final_timezone)
            logger.info(f"Created import record {import_record.id} with timezone {final_timezone}")
        else:
            # No chat messages found, but not events-only mode - this is unusual
            logger.warning(f"No chat messages found for import, but not in events-only mode")
    
    # Second pass: save all items with import_id if applicable
    chat_count = 0
    event_count = 0
    
    for item in all_parsed_items:
        if isinstance(item, ChatLog):
            if import_record:
                item.import_id = import_record.id
            db.session.add(item)
            chat_count += 1
        elif isinstance(item, ChannelEvent):
            if import_record:
                item.import_id = import_record.id
            db.session.add(item)
            event_count += 1
    
    db.session.commit()
    logger.info(f"Successfully imported {chat_count} chat messages and {event_count} events" + 
                (f" under import {import_record.id}" if import_record else " (legacy/bot import)"))
    
    return import_record


if __name__ == "__main__":
    parse_log("./chatterino_logs/logfile.log", 7)
