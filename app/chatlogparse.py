import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from .models.db import ChatLog, ChannelEvent, db
from typing import Optional, Union
from pathlib import Path
from app.logger import logger
from app.models.config import config

CEST = ZoneInfo(config.timezone)

MESSAGE_REGEX = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s+(.+): (.+)$")

START_LINE_REGEX = re.compile(
    r"# Start logging at (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})")

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


def parse_log_start_line(line: str) -> datetime:
    match = START_LINE_REGEX.match(line)
    if not match:
        raise ValueError(f"Invalid start line: {line}")
    date_str, time_str = match.groups()
    return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")


def parse_logs(folder_path: str, channel_id: int):
    log_folder = Path(folder_path)
    logger.info(f"Parsing logs from {log_folder}")
    for log_file in log_folder.glob("*.log"):
        logger.info(f"Parsing {log_file}")
        parse_log(log_file.as_posix(), channel_id)


def parse_log(log_path: str, channel_id: int):
    with Path(log_path).open("r", encoding="utf-8") as f:
        lines = f.readlines()
    if not lines or not lines[0].startswith("# Start logging at"):
        raise ValueError(
            "Log must start with '# Start logging at YYYY-MM-DD HH:MM:SS ...'")
    base_date = parse_log_start_line(lines[0])
    parser = ChatLogParser(base_date, channel_id)

    for line in lines[1:]:
        result = parser.parse_line(line)
        if isinstance(result, ChatLog):
            db.session.add(result)
            # print(f"Chat: {result.timestamp} | {result.username}: {result.message}")
        elif isinstance(result, ChannelEvent):
            db.session.add(result)
            # print(f"Event: {result.timestamp} | {result.raw_message}")
        else:
            logger.info(f"Ignored: {line.strip()}")
    db.session.commit()


if __name__ == "__main__":
    parse_log("./chatterino_logs/logfile.log", 7)
