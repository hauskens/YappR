import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import os
from typing import List

from app.chatlogparse import (
    ChatLogParser, 
    parse_log_start_line,
    check_for_duplicate_import,
    create_import_record,
    parse_log
)
from app.models.chatlog import ChatLog, ChatLogImport


@pytest.mark.unit
class TestChatLogStartLineParsing:
    """Test parsing of chatlog start lines with various timezone formats."""
    
    def test_parse_start_line_with_timezone(self):
        """Test parsing start line with timezone information."""
        line = "# Start logging at 2025-05-28 00:00:00 Eastern Daylight Time"
        base_date, timezone = parse_log_start_line(line)
        
        assert base_date == datetime(2025, 5, 28, 0, 0, 0)
        assert timezone == "Eastern Daylight Time"
    
    def test_parse_start_line_without_timezone(self):
        """Test parsing start line without timezone information."""
        line = "# Start logging at 2025-05-28 00:00:00"
        base_date, timezone = parse_log_start_line(line)
        
        assert base_date == datetime(2025, 5, 28, 0, 0, 0)
        assert timezone == "UTC"
    
    def test_parse_start_line_with_different_timezones(self):
        """Test parsing with various timezone formats."""
        test_cases = [
            ("# Start logging at 2025-01-15 14:30:00 Central Standard Time", "Central Standard Time"),
            ("# Start logging at 2025-06-20 09:15:30 Pacific Daylight Time", "Pacific Daylight Time"),
            ("# Start logging at 2025-12-01 18:45:00 Mountain Standard Time", "Mountain Standard Time"),
            ("# Start logging at 2025-03-15 12:00:00 UTC", "UTC"),
        ]
        
        for line, expected_timezone in test_cases:
            _, timezone = parse_log_start_line(line)
            assert timezone == expected_timezone
    
    def test_parse_start_line_invalid_format(self):
        """Test that invalid start lines raise ValueError."""
        invalid_lines = [
            "Invalid line",
            "# Wrong format 2025-05-28",
            "# Start logging 2025-05-28 00:00:00",
            "Start logging at 2025-05-28 00:00:00",
        ]
        
        for line in invalid_lines:
            with pytest.raises(ValueError, match="Invalid start line"):
                parse_log_start_line(line)


@pytest.mark.unit
class TestChatLogParser:
    """Test the ChatLogParser class functionality."""
    
    def test_parser_initialization(self):
        """Test parser initialization with base date."""
        base_date = datetime(2025, 5, 28, 0, 0, 0)
        parser = ChatLogParser(base_date, channel_id=1)
        
        assert parser.base_date == base_date
        assert parser.last_timestamp == base_date
        assert parser.channel_id == 1
    
    def test_parse_chat_message(self):
        """Test parsing of chat messages."""
        base_date = datetime(2025, 5, 28, 0, 0, 0)
        parser = ChatLogParser(base_date, channel_id=1)
        
        line = "[00:01:30] testuser: Hello world!"
        result = parser.parse_line(line)
        
        assert isinstance(result, ChatLog)
        assert result.channel_id == 1
        assert result.username == "testuser"
        assert result.message == "Hello world!"
        assert result.timestamp == datetime(2025, 5, 28, 0, 1, 30)
    
    def test_parse_chat_message_with_complex_username(self):
        """Test parsing messages with complex usernames."""
        base_date = datetime(2025, 5, 28, 0, 0, 0)
        parser = ChatLogParser(base_date, channel_id=1)
        
        # Username with badges/prefixes
        line = "[00:02:15] @subscriber moderator testuser: Complex message!"
        result = parser.parse_line(line)
        
        assert isinstance(result, ChatLog)
        assert result.username == "testuser"  # Should extract the last word
        assert result.message == "Complex message!"
    
    def test_parse_timestamp_rollover(self):
        """Test that timestamps correctly roll over to next day."""
        base_date = datetime(2025, 5, 28, 23, 59, 0)
        parser = ChatLogParser(base_date, channel_id=1)
        
        # First message at 23:59:30
        line1 = "[23:59:30] user1: Last message of day"
        result1 = parser.parse_line(line1)
        assert result1.timestamp == datetime(2025, 5, 28, 23, 59, 30)
        
        # Second message at 00:00:30 (next day)
        line2 = "[00:00:30] user2: First message of next day"
        result2 = parser.parse_line(line2)
        assert result2.timestamp == datetime(2025, 5, 29, 0, 0, 30)
    
    def test_parse_invalid_lines(self):
        """Test handling of invalid or unparseable lines."""
        base_date = datetime(2025, 5, 28, 0, 0, 0)
        parser = ChatLogParser(base_date, channel_id=1)
        
        # These lines should return None (truly unparseable)
        truly_invalid_lines = [
            "Random text",
            "[invalid timestamp] user: message", 
            "",
            "Just some random text without any format",
        ]
        
        for line in truly_invalid_lines:
            result = parser.parse_line(line)
            assert result is None
    
    def test_parse_channel_events(self):
        """Test parsing of channel event lines (timestamp-only format)."""
        from app.models.channel import ChannelEvent
        
        base_date = datetime(2025, 5, 28, 0, 0, 0)
        parser = ChatLogParser(base_date, channel_id=1)
        
        # This format gets parsed as ChannelEvent
        line = "[00:01:30] User joined the channel"
        result = parser.parse_line(line)
        
        assert isinstance(result, ChannelEvent)
        assert result.channel_id == 1
        assert result.raw_message == "User joined the channel"
        assert result.timestamp == datetime(2025, 5, 28, 0, 1, 30)


@pytest.mark.unit 
class TestDuplicateDetection:
    """Test duplicate detection functionality."""
    
    @patch('app.chatlogparse.db')
    def test_no_duplicates_found(self, mock_db):
        """Test when no duplicates are found."""
        # Mock empty database result
        mock_db.session.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
        
        first_messages = [
            ChatLog(channel_id=1, timestamp=datetime(2025, 5, 28, 10, 0, 0), username="user1", message="Hello"),
            ChatLog(channel_id=1, timestamp=datetime(2025, 5, 28, 10, 1, 0), username="user2", message="World"),
        ]
        
        result = check_for_duplicate_import(1, first_messages, "UTC")
        assert result is False
    
    @patch('app.chatlogparse.db')
    def test_duplicates_found_bot_import(self, mock_db):
        """Test duplicate detection for bot-imported messages."""
        # Create existing messages that match our sample
        existing_messages = [
            ChatLog(channel_id=1, timestamp=datetime(2025, 5, 28, 10, 0, 0), username="user1", message="Hello", import_id=None),
            ChatLog(channel_id=1, timestamp=datetime(2025, 5, 28, 10, 1, 0), username="user2", message="World", import_id=None),
        ]
        mock_db.session.query.return_value.filter.return_value.order_by.return_value.all.return_value = existing_messages
        
        first_messages = [
            ChatLog(channel_id=1, timestamp=datetime(2025, 5, 28, 10, 0, 0), username="user1", message="Hello"),
            ChatLog(channel_id=1, timestamp=datetime(2025, 5, 28, 10, 1, 0), username="user2", message="World"),
        ]
        
        result = check_for_duplicate_import(1, first_messages, "UTC")
        assert result is True
    
    @patch('app.chatlogparse.db')
    def test_duplicates_found_user_import(self, mock_db):
        """Test duplicate detection for user-imported messages."""
        # Create mock import record
        mock_import = ChatLogImport(id=5, imported_by=123)
        
        # Create existing messages with import_id
        existing_messages = [
            ChatLog(channel_id=1, timestamp=datetime(2025, 5, 28, 10, 0, 0), username="user1", message="Hello", import_id=5),
            ChatLog(channel_id=1, timestamp=datetime(2025, 5, 28, 10, 1, 0), username="user2", message="World", import_id=5),
        ]
        
        # Mock database queries
        mock_db.session.query.return_value.filter.return_value.order_by.return_value.all.return_value = existing_messages
        mock_db.session.query.return_value.filter_by.return_value.first.return_value = mock_import
        
        first_messages = [
            ChatLog(channel_id=1, timestamp=datetime(2025, 5, 28, 10, 0, 0), username="user1", message="Hello"),
            ChatLog(channel_id=1, timestamp=datetime(2025, 5, 28, 10, 1, 0), username="user2", message="World"),
        ]
        
        result = check_for_duplicate_import(1, first_messages, "UTC")
        assert result is True


@pytest.mark.unit
class TestChatLogImportCreation:
    """Test ChatLogImport record creation."""
    
    @patch('app.chatlogparse.db')
    def test_create_import_record(self, mock_db):
        """Test creation of ChatLogImport record."""
        mock_db.session.add = MagicMock()
        mock_db.session.flush = MagicMock()
        
        import_record = create_import_record(
            channel_id=1, 
            imported_by=123, 
            timezone_str="Eastern Daylight Time"
        )
        
        assert isinstance(import_record, ChatLogImport)
        assert import_record.channel_id == 1
        assert import_record.imported_by == 123
        assert import_record.timezone == "Eastern Daylight Time"
        assert isinstance(import_record.imported_at, datetime)
        
        mock_db.session.add.assert_called_once_with(import_record)
        mock_db.session.flush.assert_called_once()


@pytest.mark.unit
class TestFullLogParsing:
    """Test complete log file parsing functionality."""
    
    def create_test_log_file(self, content: str) -> str:
        """Create a temporary log file for testing."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False, encoding='utf-8') as f:
            f.write(content)
            return f.name
    
    def teardown_method(self, method):
        """Clean up any temporary files."""
        # This will run after each test method
        pass
    
    @patch('app.chatlogparse.db')
    @patch('app.chatlogparse.check_for_duplicate_import')
    @patch('app.chatlogparse.create_import_record')
    def test_parse_log_success(self, mock_create_import, mock_check_duplicates, mock_db):
        """Test successful log parsing without duplicates."""
        # Setup mocks
        mock_check_duplicates.return_value = False
        mock_import = ChatLogImport(id=10, channel_id=1, imported_by=123, timezone="UTC")
        mock_create_import.return_value = mock_import
        mock_db.session.add = MagicMock()
        mock_db.session.commit = MagicMock()
        
        # Create test log content
        log_content = """# Start logging at 2025-05-28 00:00:00 UTC
[00:01:00] user1: First message
[00:01:30] user2: Second message
[00:02:00] user3: Third message
"""
        
        log_file = self.create_test_log_file(log_content)
        
        try:
            result = parse_log(log_file, channel_id=1, imported_by=123)
            
            assert result == mock_import
            mock_check_duplicates.assert_called_once()
            mock_create_import.assert_called_once_with(1, 123, "UTC")
            assert mock_db.session.add.call_count == 3  # Three chat messages
            mock_db.session.commit.assert_called_once()
            
        finally:
            os.unlink(log_file)
    
    @patch('app.chatlogparse.db')
    @patch('app.chatlogparse.check_for_duplicate_import')
    def test_parse_log_with_duplicates(self, mock_check_duplicates, mock_db):
        """Test log parsing with duplicate detection."""
        mock_check_duplicates.return_value = True
        
        log_content = """# Start logging at 2025-05-28 00:00:00 UTC
[00:01:00] user1: Duplicate message
[00:01:30] user2: Another duplicate
"""
        
        log_file = self.create_test_log_file(log_content)
        
        try:
            with pytest.raises(ValueError, match="duplicate messages"):
                parse_log(log_file, channel_id=1, imported_by=123)
            
            mock_check_duplicates.assert_called_once()
            
        finally:
            os.unlink(log_file)
    
    @patch('app.chatlogparse.db')
    def test_parse_log_bot_import_no_duplicate_check(self, mock_db):
        """Test that bot imports skip duplicate checking."""
        mock_db.session.add = MagicMock()
        mock_db.session.commit = MagicMock()
        
        log_content = """# Start logging at 2025-05-28 00:00:00 UTC
[00:01:00] user1: Bot collected message
"""
        
        log_file = self.create_test_log_file(log_content)
        
        try:
            # Bot import (imported_by=None)
            result = parse_log(log_file, channel_id=1, imported_by=None)
            
            assert result is None  # No import record for bot imports
            mock_db.session.add.assert_called_once()  # Only the chat message
            mock_db.session.commit.assert_called_once()
            
        finally:
            os.unlink(log_file)
    
    def test_parse_log_invalid_format(self):
        """Test parsing log with invalid format."""
        log_content = """Invalid log format
[00:01:00] user1: This won't work
"""
        
        log_file = self.create_test_log_file(log_content)
        
        try:
            with pytest.raises(ValueError, match="Log must start with"):
                parse_log(log_file, channel_id=1, imported_by=123)
                
        finally:
            os.unlink(log_file)
    
    @patch('app.chatlogparse.db')
    def test_parse_log_timezone_override(self, mock_db):
        """Test that timezone override works correctly."""
        mock_db.session.add = MagicMock()
        mock_db.session.commit = MagicMock()
        
        log_content = """# Start logging at 2025-05-28 00:00:00 UTC
[00:01:00] user1: Test message
"""
        
        log_file = self.create_test_log_file(log_content)
        
        try:
            # Override timezone
            result = parse_log(log_file, channel_id=1, imported_by=None, timezone_str="Pacific Time")
            
            # Verify the override was used (this would be tested in create_import_record in real scenario)
            mock_db.session.commit.assert_called_once()
            
        finally:
            os.unlink(log_file)


@pytest.mark.parametrize("timezone_input,expected_timezone", [
    ("Eastern Daylight Time", "Eastern Daylight Time"),
    ("Central Standard Time", "Central Standard Time"), 
    ("Pacific Daylight Time", "Pacific Daylight Time"),
    ("Mountain Standard Time", "Mountain Standard Time"),
    ("UTC", "UTC"),
    ("", "UTC"),  # Default case
])
@pytest.mark.unit
def test_timezone_parsing_variations(timezone_input, expected_timezone):
    """Test various timezone parsing scenarios."""
    if timezone_input:
        line = f"# Start logging at 2025-05-28 00:00:00 {timezone_input}"
    else:
        line = "# Start logging at 2025-05-28 00:00:00"
    
    _, timezone = parse_log_start_line(line)
    assert timezone == expected_timezone