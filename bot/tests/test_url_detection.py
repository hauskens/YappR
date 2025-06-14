import sys
import os
import unittest
import asyncio
from unittest.mock import MagicMock, patch
from datetime import datetime

# Add parent directory to path to import bot module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from bot.main import TwitchBot
from twitchAPI.chat import ChatMessage


class TestUrlDetection(unittest.TestCase):
    def setUp(self):
        """Set up test environment before each test"""
        self.bot = TwitchBot()
        # Mock the SessionLocal to avoid actual database operations
        self.session_mock = MagicMock()
        self.session_mock_instance = MagicMock()
        self.session_mock.return_value = self.session_mock_instance
        
        # Set up some test data
        self.channel_id = 123
        self.room_id = "456"
        self.bot.enabled_channels = {self.room_id: self.channel_id}
        
        # Mock the database session
        self.patcher = patch('bot.main.SessionLocal', self.session_mock)
        self.patcher.start()
        
        # Create a mock for the session buffer
        self.bot.session = MagicMock()
        self.bot.message_buffer = []

    def tearDown(self):
        """Clean up after each test"""
        self.patcher.stop()

    def test_url_pattern_detection(self):
        """Test that the URL pattern correctly identifies URLs"""
        # Test cases with URLs that should be detected
        test_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "http://youtu.be/dQw4w9WgXcQ",
            "https://youtu.be/SfT4FMkh1-w?feature=shared&t=17",
            "https://www.youtube.com/watch?v=SfT4FMkh1-w",
            "https://www.twitch.tv/videos/123456789?t=10h01m21s",
            "https://clips.twitch.tv/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR",
            "https://www.twitch.tv/brittt/clip/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR?filter=clips&range=all&sort=time",
        ]
        
        for url in test_urls:
            matches = self.bot.URL_PATTERN.findall(url)
            self.assertEqual(len(matches), 1, f"URL pattern should detect: {url}")
            self.assertEqual(matches[0], url, f"URL pattern should extract full URL: {url}")
        
        # Test cases with text containing URLs
        test_messages = [
            "Check out this video: https://www.youtube.com/watch?v=dQw4w9WgXcQ it's great!",
            "I was watching http://youtu.be/dQw4w9WgXcQ yesterday",
            "https://clips.twitch.tv/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR",
        ]
        
        for message in test_messages:
            matches = self.bot.URL_PATTERN.findall(message)
            self.assertEqual(len(matches), 1, f"URL pattern should detect URL in: {message}")
    
    def test_supported_platform_detection(self):
        """Test that supported platforms are correctly identified"""
        # Test cases for supported platforms
        supported_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "http://youtu.be/dQw4w9WgXcQ",
            "https://youtu.be/SfT4FMkh1-w?feature=shared&t=17",
            "https://www.youtube.com/watch?v=SfT4FMkh1-w",
            "https://www.twitch.tv/videos/123456789?t=10h01m21s",
            "https://clips.twitch.tv/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR",
        ]
        
        for url in supported_urls:
            self.assertTrue(
                self.bot.get_platform(url),
                f"URL should be identified as supported: {url}"
            )
        
        # Test cases for unsupported platforms
        unsupported_urls = [
            "https://www.example.com",
            "http://github.com/user/repo",
            "https://twitter.com/username",
            "https://www.youtube.com/@WirtualTV",
            "https://www.twitch.tv/fanfan",
            "https://www.twitch.tv/videos/123456789",
            "https://arazu.io/t3_1kxypp9",
        ]
        
        for url in unsupported_urls:
            self.assertFalse(
                self.bot.get_platform(url),
                f"URL should be identified as unsupported: {url}"
            )

    def test_add_to_content_queue(self):
        """Test adding a URL to the content queue"""
        # Create test data
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        username = "test_user"
        external_user_id = "12345"
        
        # Create mock objects for our database entities
        mock_content = MagicMock()
        mock_content.id = 999
        
        mock_queue_item = MagicMock()
        mock_queue_item.id = 888
        
        mock_user = MagicMock()
        mock_user.id = 777
        
        # Setup the session mock to return None for all queries (indicating objects don't exist)
        mock_none_result = MagicMock()
        mock_none_result.one_or_none.return_value = None
        
        mock_scalars = MagicMock()
        mock_scalars.return_value = mock_none_result
        
        # We need to patch the select function and the Content/ExternalUser/ContentQueue classes
        # to avoid SQLAlchemy errors
        with patch('bot.main.select') as mock_select, \
             patch('bot.main.Content') as mock_content_class, \
             patch('bot.main.ContentQueue') as mock_queue_class, \
             patch('bot.main.ExternalUser') as mock_user_class, \
             patch('bot.main.ContentQueueSubmission') as mock_submission_class:
            
            # Configure the mocks to return our mock objects
            mock_content_class.return_value = mock_content
            mock_queue_class.return_value = mock_queue_item
            mock_user_class.return_value = mock_user
            
            # Make select() return a mock query object that can be used in filter()
            mock_query = MagicMock()
            mock_select.return_value = mock_query
            mock_query.filter.return_value = mock_query
            
            # Make the session.execute() return our prepared mock results
            self.session_mock_instance.execute.return_value.scalars.return_value.one_or_none.return_value = None
            
            # Call the method
            self.bot.add_to_content_queue(url, self.channel_id, username, external_user_id)
            
            # Verify select was called
            mock_select.assert_called()
            
            # Verify Content was created with the right URL
            mock_content_class.assert_called_once_with(url=url)
            
            # Verify objects were added to the session
            self.session_mock_instance.add.assert_any_call(mock_content)
            self.session_mock_instance.add.assert_any_call(mock_user)
            self.session_mock_instance.add.assert_any_call(mock_queue_item)
            
            # Verify session was committed
            self.session_mock_instance.commit.assert_called_once()

    @patch('bot.main.TwitchBot.add_to_content_queue')
    def test_on_message_with_url(self, mock_add_to_queue):
        """Test handling a message containing a URL"""
        # Create a mock ChatMessage
        mock_message = MagicMock(spec=ChatMessage)
        mock_message.room = MagicMock()
        mock_message.room.room_id = self.room_id
        mock_message.room.name = "test_channel"
        mock_message.user = MagicMock()
        mock_message.user.name = "test_user"
        mock_message.user.id = "12345"
        mock_message.text = "Check out this video: https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        mock_message.sent_timestamp = int(datetime.now().timestamp() * 1000)
        
        # Call on_message using asyncio.run
        asyncio.run(self.bot.on_message(mock_message))
        
        # Verify add_to_content_queue was called with correct parameters
        mock_add_to_queue.assert_called_once_with(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            channel_id=self.channel_id,
            username="test_user",
            external_user_id="12345"
        )
        
        # Verify chat log was added to session
        self.bot.session.add.assert_called_once()
        self.assertEqual(len(self.bot.message_buffer), 1)


if __name__ == '__main__':
    unittest.main()
