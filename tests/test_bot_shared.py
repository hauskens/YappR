import pytest
import re
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime
import pytest_asyncio


# Mark the entire module as unit tests that don't need DB setup
pytestmark = pytest.mark.unit

# Patch the engine and session before importing bot.shared
with patch('sqlalchemy.create_engine'):
    from bot.shared import (
        get_platform, sanitize_youtube_url, BotTaskManager, 
        fetch_youtube_data, fetch_youtube_clip_data,
        fetch_twitch_video_data, fetch_twitch_clip_data,
        sanitize_twitch_url,
        ContentDict, supported_platforms, add_to_content_queue,
        task_manager
    )

from app.models.db import (
    ContentQueueSubmissionSource, AccountSource, Content, 
    ContentQueue, ExternalUser, ExternalUserWeight,
    ContentQueueSubmission
)
from app.twitch_api import Twitch


class TestGetPlatform:
    """Tests that we identify the correct platform with the get_platform function"""

    @pytest.mark.parametrize("url,expected", [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=123", "youtube"),
        ("https://youtu.be/dQw4w9WgXcQ", "youtube"),
        ('https://youtu.be/dQw4w9WgXcQ?feature=shared&t=44', "youtube"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "youtube_short"),
        ("https://www.youtube.com/clip/UgkxFyeXQtfPRff43kUWbsAeuBND6Lb4ysEM", "youtube_clip"),
        ("https://twitch.tv/videos/123456789?t=1h2m3s", "twitch_video"),
        ("https://clips.twitch.tv/CleverClipName", "twitch_clip"),
        ("https://twitch.tv/broadcaster/clip/CleverClipName", "twitch_clip"),
        ("https://clips.twitch.tv/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR", "twitch_clip"),
        ('https://www.twitch.tv/my_supreme_streamer', None),
        ("https://example.com", None),
        ('https://www.youtube.com/@RickAstleyYT', None),
        ("not a url", None),
    ])
    def test_get_platform(self, url, expected):
        """Test that platforms are correctly identified from URLs"""
        assert get_platform(url) == expected


class TestSanitizeUrl:
    """Tests for the sanitize_url function"""

    @pytest.mark.parametrize("url,expected", [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=123", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        ('https://youtu.be/dQw4w9WgXcQ?feature=shared&t=44', "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        ('https://www.youtube.com/shorts/dQw4w9WgXcQ', "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        ("https://www.youtube.com/clip/UgkxFyeXQtfPRff43kUWbsAeuBND6Lb4ysEM", "https://www.youtube.com/clip/UgkxFyeXQtfPRff43kUWbsAeuBND6Lb4ysEM"),
        ("https://www.youtube.com/clip/UgkxFyeXQtfPRff43kUWbsAeuBND6Lb4ysEM?t=1h2m3s", "https://www.youtube.com/clip/UgkxFyeXQtfPRff43kUWbsAeuBND6Lb4ysEM"),
    ])
    def test_sanitize_url_youtube(self, url, expected):
        """Test that URLs are properly sanitized by removing query params and fragments"""
        assert sanitize_youtube_url(url) == expected

    @pytest.mark.parametrize("url", [
        "https://example.com/page?param=value#section",
        "https://example.com/page",
    ])
    def test_sanitize_url_youtube_invalid(self, url):
        """Test that invalid URLs are handled correctly"""
        with pytest.raises(ValueError):
            sanitize_youtube_url(url)

    @pytest.mark.parametrize("url,expected", [
        ("https://www.twitch.tv/videos/123456789?t=1h2m3s", "https://www.twitch.tv/videos/123456789"),
        ("https://clips.twitch.tv/CleverClipName?t=1h2m3s", "https://clips.twitch.tv/CleverClipName"),
        ("https://twitch.tv/broadcaster/clip/CleverClipName?t=1h2m3s", "https://clips.twitch.tv/CleverClipName"),
        ("https://clips.twitch.tv/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR?t=1h2m3s", "https://clips.twitch.tv/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR"),
        ("https://twitch.tv/brittt/clip/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR", "https://clips.twitch.tv/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR"),
    ])
    def test_sanitize_url_twitch(self, url, expected):
        """Test that URLs are properly sanitized by removing query params and fragments"""
        assert sanitize_twitch_url(url) == expected


@pytest.fixture
def mock_youtube_video():
    """Mock YouTube video response"""
    video = MagicMock()
    video.snippet.title = "Test YouTube Video"
    video.snippet.channelTitle = "Test Channel"
    video.snippet.publishedAt = datetime.now()
    video.contentDetails.duration.total_seconds.return_value = 300
    return video


@pytest.fixture
def mock_twitch_video():
    """Mock Twitch video response"""
    video = MagicMock()
    video.title = "Test Twitch Video"
    video.user_name = "Test User"
    video.thumbnail_url = "https://example.com/thumbnail.jpg"
    video.created_at = datetime.now()
    video.duration = "5m0s"
    return video


@pytest.fixture
def mock_twitch_clip():
    """Mock Twitch clip response"""
    clip = MagicMock()
    clip.title = "Test Twitch Clip"
    clip.broadcaster_name = "Test Broadcaster"
    clip.creator_name = "Test Creator"
    clip.thumbnail_url = "https://example.com/thumbnail.jpg"
    clip.created_at = datetime.now()
    clip.duration = 30
    return clip


class TestYouTubeFetching:
    """Tests for the YouTube data fetching functions"""

    @pytest.mark.asyncio
    @patch("bot.shared.get_youtube_video_id")
    @patch("bot.shared.get_videos")
    @patch("bot.shared.get_youtube_thumbnail_url")
    async def test_fetch_youtube_data(self, mock_get_thumbnail, mock_get_videos, mock_get_id, mock_youtube_video):
        """Test fetching YouTube video data"""
        mock_get_id.return_value = "dQw4w9WgXcQ"
        mock_get_videos.return_value = [mock_youtube_video]
        mock_get_thumbnail.return_value = "https://example.com/thumbnail.jpg"
        
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        result = await fetch_youtube_data(url)
        
        # Check that result has the expected structure instead of using isinstance with TypedDict
        assert isinstance(result, dict)
        # Verify the dictionary has the required keys from ContentDict
        required_keys = ['url', 'title', 'channel_name', 'thumbnail_url', 'duration']
        assert all(key in result for key in required_keys)
        assert result["url"] == url
        assert result["title"] == "Test YouTube Video"
        assert result["channel_name"] == "Test Channel"
        assert result["thumbnail_url"] == "https://example.com/thumbnail.jpg"
        assert result["duration"] == 300
        
        mock_get_id.assert_called_once_with(url)
        mock_get_videos.assert_called_once_with(["dQw4w9WgXcQ"])
        mock_get_thumbnail.assert_called_once_with(url)


class TestBotTaskManager:
    """Tests for the BotTaskManager class"""

    def test_init(self):
        """Test initialization of BotTaskManager"""
        task_manager = BotTaskManager()
        
        assert not task_manager.running
        assert task_manager.poll_interval == 1
        assert isinstance(task_manager.components, dict)
        assert len(task_manager.task_handlers) > 0
        assert "create_clip" in task_manager.task_handlers

    def test_register_component(self):
        """Test component registration"""
        task_manager = BotTaskManager()
        component = MagicMock()
        
        task_manager.register_component("test", component)
        
        assert "test" in task_manager.components
        assert task_manager.components["test"] == component


class TestAddToContentQueue:
    """Tests for the add_to_content_queue function"""

    @pytest.fixture
    def mock_session(self):
        """Mock SQLAlchemy session"""
        session = MagicMock()
        patcher = patch('bot.shared.SessionLocal', return_value=session)
        patcher.start()
        yield session
        patcher.stop()

    @pytest.fixture
    def mock_platform_data(self):
        """Mock platform data for content fetching"""
        return {
            'sanitized_url': 'https://www.youtube.com/watch',
            'title': 'Test Video',
            'duration': 300,
            'thumbnail_url': 'https://example.com/thumbnail.jpg',
            'channel_name': 'Test Channel',
            'author': None,
            'created_at': datetime.now()
        }

    @pytest.mark.asyncio
    @patch('bot.shared.get_platform')
    @patch('bot.shared.fetch_youtube_data')
    async def test_add_to_content_queue_new_content(self, mock_fetch_data, mock_get_platform, mock_session, mock_platform_data):
        """Test adding new content to the queue"""
        # Setup mocks
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        broadcaster_id = 123456789
        username = "test_user"
        external_user_id = "987654321"
        submission_source = ContentQueueSubmissionSource.Twitch
        submission_source_id = 1
        
        mock_get_platform.return_value = "youtube"
        mock_fetch_data.return_value = ContentDict(
            url=url,
            sanitized_url=mock_platform_data['sanitized_url'],
            title=mock_platform_data['title'],
            duration=mock_platform_data['duration'],
            thumbnail_url=mock_platform_data['thumbnail_url'],
            channel_name=mock_platform_data['channel_name'],
            author=mock_platform_data['author'],
            created_at=mock_platform_data['created_at']
        )
        
        # Mock session query results for the add_to_content_queue function
        mock_session.execute.return_value.scalars.return_value.one_or_none.side_effect = [
            None,  # Content doesn't exist
            None,  # External user doesn't exist
            None,  # External user weight doesn't exist
            None,  # Existing queue item doesn't exist (ContentQueue query)
            None   # Possibly for submission check
        ]
        
        # Call function
        await add_to_content_queue(
            url=url,
            broadcaster_id=broadcaster_id,
            username=username,
            external_user_id=external_user_id,
            submission_source_type=submission_source,
            submission_source_id=submission_source_id,
            session=mock_session
        )
        
        # Verify interactions
        mock_get_platform.assert_called_once_with(url)
        mock_fetch_data.assert_called_once_with(url)
        
        # Check that content was created
        content_add_call = mock_session.add.call_args_list[0]
        content = content_add_call[0][0]
        assert isinstance(content, Content)
        assert content.url == url
        assert content.title == mock_platform_data['title']
        
        # Check that external user was created
        user_add_call = mock_session.add.call_args_list[1]
        user = user_add_call[0][0]
        assert isinstance(user, ExternalUser)
        assert user.username == username
        assert user.external_account_id == int(external_user_id)
        
        # Check that queue item and submission were created
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    @patch('bot.shared.get_platform')
    @patch('bot.shared.fetch_youtube_data')
    async def test_add_to_content_queue_existing_content(self, mock_fetch_data, mock_get_platform, mock_session):
        """Test adding existing content to the queue"""
        # Setup mocks
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        broadcaster_id = 123456789
        username = "test_user"
        external_user_id = "987654321"
        submission_source = ContentQueueSubmissionSource.Twitch
        submission_source_id = 1
        
        mock_get_platform.return_value = "youtube"
        
        # Mock existing content and queue item
        existing_content = MagicMock(spec=Content)
        existing_content.id = 42
        
        existing_user = MagicMock(spec=ExternalUser)
        existing_user.id = 24
        
        existing_weight = MagicMock(spec=ExternalUserWeight)
        existing_weight.id = 12
        existing_weight.banned = False
        
        existing_queue_item = None  # Content exists but not in queue
        
        # Mock session query results
        mock_session.execute.return_value.scalars.return_value.one_or_none.side_effect = [
            existing_content,  # Content exists
            existing_queue_item,  # Not in queue yet
            existing_user,  # External user exists
            existing_weight  # External user weight exists
        ]
        
        # Call function
        await add_to_content_queue(
            url=url,
            broadcaster_id=broadcaster_id,
            username=username,
            external_user_id=external_user_id,
            submission_source_type=submission_source,
            submission_source_id=submission_source_id,
            session=mock_session
        )
        
        # Verify interactions
        mock_get_platform.assert_called_once_with(url)
        mock_fetch_data.assert_not_called()  # Should not fetch data for existing content
        
        # Check that a new queue item was created
        queue_add_call = mock_session.add.call_args_list[0]
        queue_item = queue_add_call[0][0]
        assert isinstance(queue_item, ContentQueue)
        assert queue_item.content_id == existing_content.id
        assert queue_item.broadcaster_id == broadcaster_id
        
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    @patch('bot.shared.get_platform')
    async def test_add_to_content_queue_unsupported_platform(self, mock_get_platform, mock_session):
        """Test adding content from unsupported platform"""
        # Setup mocks
        url = "https://example.com/video"
        broadcaster_id = 123456789
        username = "test_user"
        external_user_id = "987654321"
        submission_source = ContentQueueSubmissionSource.Twitch
        submission_source_id = 1
        
        mock_get_platform.return_value = None  # Unsupported platform
        
        # Call function
        await add_to_content_queue(
            url=url,
            broadcaster_id=broadcaster_id,
            username=username,
            external_user_id=external_user_id,
            submission_source_type=submission_source,
            submission_source_id=submission_source_id,
            session=mock_session
        )
        
        # Verify interactions
        mock_get_platform.assert_called_once_with(url)
        mock_session.add.assert_not_called()  # Nothing should be added
        mock_session.commit.assert_not_called()  # No database changes
