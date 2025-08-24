import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from app.models import db
from app.models import ChatLog, ChannelEvent, ChatLogImport
from typing import Optional, Union, List
from pathlib import Path
from app.logger import logger
from app.models.config import config
from sqlalchemy import and_, func

CEST = ZoneInfo(config.timezone)

MESSAGE_REGEX = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s+(.+): (.+)$")

START_LINE_REGEX = re.compile(
    r"# Start logging at (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})(?: (.+))?")

TIMESTAMP_ONLY_REGEX = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\] (.+)$")


class ChatLogParser:
    def __init__(self, base_date: datetime, channel_id: int):
        self.base_date = base_date
        self.last_timestamp = base_date
        self.channel_id = channel_id

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
                return ChannelEvent(
                    channel_id=self.channel_id,
                    timestamp=full_timestamp,
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

        self.last_timestamp = combined
        return combined


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
    Check if these messages already exist by comparing the first 10 messages
    within a 24-hour window around the timestamp range.
    Returns True if duplicates are found (regardless of import source), False otherwise.
    """
    if not first_messages:
        return False
    
    # Get the timestamp range of our sample messages
    start_time = first_messages[0].timestamp
    end_time = first_messages[-1].timestamp
    
    # Create 24-hour buffer around our sample timeframe
    search_start = start_time - timedelta(hours=24)
    search_end = end_time + timedelta(hours=24)
    
    logger.info(f"Checking for duplicates in timeframe {search_start} to {search_end}")
    
    # Get existing messages in the extended timeframe
    existing_messages = db.session.query(ChatLog).filter(
        and_(
            ChatLog.channel_id == channel_id,
            ChatLog.timestamp >= search_start,
            ChatLog.timestamp <= search_end
        )
    ).order_by(ChatLog.timestamp).all()
    
    if len(existing_messages) < len(first_messages):
        return False
    
    # Convert first messages to comparison tuples (username, message)
    sample_tuples = [(msg.username, msg.message) for msg in first_messages]
    
    # Sliding window search through existing messages
    for i in range(len(existing_messages) - len(first_messages) + 1):
        window_tuples = [(existing_messages[i + j].username, existing_messages[i + j].message) 
                        for j in range(len(first_messages))]
        
        if sample_tuples == window_tuples:
            # Found matching sequence - determine the source
            matching_messages = existing_messages[i:i + len(first_messages)]
            import_source = "bot/live collection"
            
            # Check if any message has an import_id to identify user import
            for msg in matching_messages:
                if msg.import_id:
                    import_record = db.session.query(ChatLogImport).filter_by(id=msg.import_id).first()
                    if import_record:
                        import_source = f"user import {import_record.id} by user {import_record.imported_by} at {import_record.imported_at}"
                    break
            
            logger.warning(f"Found duplicate messages from {import_source}")
            return True
    
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


def parse_log(log_path: str, channel_id: int, imported_by: int | None = None, timezone_str: str | None = None):
    """
    Parse a chat log file and import it with duplicate detection.
    
    Args:
        log_path: Path to the log file
        channel_id: Channel ID to associate messages with
        imported_by: User ID who is importing (None for legacy/bot imports)
        timezone_str: Override timezone string (None to auto-detect from file)
    """
    with Path(log_path).open("r", encoding="utf-8") as f:
        lines = f.readlines()
    if not lines or not lines[0].startswith("# Start logging at"):
        raise ValueError(
            "Log must start with '# Start logging at YYYY-MM-DD HH:MM:SS ...'")
    
    base_date, detected_timezone = parse_log_start_line(lines[0])
    # Use provided timezone or fall back to detected timezone
    final_timezone = timezone_str or detected_timezone
    parser = ChatLogParser(base_date, channel_id)

    # First pass: parse first 10 chat messages for duplicate detection
    first_chat_messages: list[ChatLog] = []
    all_parsed_items: list[ChatLog | ChannelEvent] = []
    
    logger.info(f"Parsing {len(lines)-1} lines from {log_path}")
    
    for line in lines[1:]:
        result = parser.parse_line(line)
        if result:
            all_parsed_items.append(result)
            if isinstance(result, ChatLog) and len(first_chat_messages) < 10:
                first_chat_messages.append(result)
    
    # Check for duplicates only if we have an imported_by user (i.e., user import, not bot)
    import_record = None
    if imported_by and first_chat_messages:
        has_duplicates = check_for_duplicate_import(channel_id, first_chat_messages, final_timezone)
        if has_duplicates:
            raise ValueError(f"This log appears to contain duplicate messages that already exist in the database (from bot collection or previous import)")
        
        # Create import record
        import_record = create_import_record(channel_id, imported_by, final_timezone)
        logger.info(f"Created import record {import_record.id} with timezone {final_timezone}")
    
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
            db.session.add(item)
            event_count += 1
    
    db.session.commit()
    logger.info(f"Successfully imported {chat_count} chat messages and {event_count} events" + 
                (f" under import {import_record.id}" if import_record else " (legacy/bot import)"))
    
    return import_record


if __name__ == "__main__":
    parse_log("./chatterino_logs/logfile.log", 7)
