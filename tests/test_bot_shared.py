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
        BotTaskManager, 
        Content, add_to_content_queue,
    )
    from app.platforms.handler import PlatformRegistry, ContentDict, PlatformHandler

from app.models.content_queue_settings import ContentQueueSettings
from app.models.content_queue import ContentQueueSubmissionSource, ContentQueue
from app.models.user import ExternalUser, ExternalUserWeight


class TestSanitizeUrl:
    """Tests for the deduplicate_url function"""

    @pytest.mark.parametrize("url,expected", [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=123", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        ('https://youtu.be/dQw4w9WgXcQ?feature=shared&t=44', "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    ])
    def test_deduplicate_url_youtube_video(self, url, expected):
        """Test that URLs are properly sanitized by removing query params and fragments"""
        handler: PlatformHandler = PlatformRegistry.get_handler_by_url(url)
        assert handler.deduplicate_url() == expected

    @pytest.mark.parametrize("url,expected", [
        ('https://www.youtube.com/shorts/dQw4w9WgXcQ', "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    ])
    def test_deduplicate_url_youtube_short(self, url, expected):
        """Test that URLs are properly sanitized by removing query params and fragments"""
        handler: PlatformHandler = PlatformRegistry.get_handler_by_url(url)
        assert handler.deduplicate_url() == expected
    
    @pytest.mark.parametrize("url,expected", [
        ("https://www.youtube.com/clip/UgkxFyeXQtfPRff43kUWbsAeuBND6Lb4ysEM", "https://www.youtube.com/clip/UgkxFyeXQtfPRff43kUWbsAeuBND6Lb4ysEM"),
        ("https://www.youtube.com/clip/UgkxFyeXQtfPRff43kUWbsAeuBND6Lb4ysEM?t=1h2m3s", "https://www.youtube.com/clip/UgkxFyeXQtfPRff43kUWbsAeuBND6Lb4ysEM"),
    ])
    def test_deduplicate_url_youtube_clip(self, url: str, expected: str) -> None:
        """Test that URLs are properly sanitized by removing query params and fragments"""
        handler: PlatformHandler = PlatformRegistry.get_handler_by_url(url)
        assert handler.deduplicate_url() == expected

    @pytest.mark.parametrize("url", [
        "https://example.com/page?param=value#section",
        "https://example.com/page",
    ])
    def test_deduplicate_url_youtube_invalid(self, url):
        """Test that invalid URLs are handled correctly"""
        with pytest.raises(ValueError):
            PlatformRegistry.get_handler_by_url(url).deduplicate_url()

    @pytest.mark.parametrize("url,expected", [
        ("https://www.twitch.tv/videos/123456789?t=1h2m3s", "https://www.twitch.tv/videos/123456789"),
        ("https://www.twitch.tv/videos/123456789", "https://www.twitch.tv/videos/123456789"),
    ])
    def test_deduplicate_url_twitch_video(self, url, expected):
        """Test that URLs are properly sanitized by removing query params and fragments"""
        assert PlatformRegistry.get_handler_by_url(url).deduplicate_url() == expected

    @pytest.mark.parametrize("url,expected", [
        ("https://clips.twitch.tv/CleverClipName?t=1h2m3s", "https://clips.twitch.tv/CleverClipName"),
        ("https://twitch.tv/broadcaster/clip/CleverClipName?t=1h2m3s", "https://clips.twitch.tv/CleverClipName"),
        ("https://clips.twitch.tv/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR?t=1h2m3s", "https://clips.twitch.tv/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR"),
        ("https://twitch.tv/brittt/clip/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR", "https://clips.twitch.tv/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR"),
    ])
    def test_deduplicate_url_twitch_clip(self, url, expected):
        """Test that URLs are properly sanitized by removing query params and fragments"""
        assert PlatformRegistry.get_handler_by_url(url).deduplicate_url() == expected


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
            'deduplicated_url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            'title': 'Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster)',
            'duration': 420,
            'thumbnail_url': 'https://example.com/thumbnail.jpg',
            'channel_name': 'RickAstleyYT',
            'author': None,
            'created_at': datetime.now()
        }

    @pytest.mark.asyncio
    @patch('bot.shared.get_platform')
    async def test_add_to_content_queue_new_content(self, mock_fetch_data, mock_session, mock_platform_data):
        """Test adding new content to the queue"""
        # Setup mocks
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        broadcaster_id = 123456789
        username = "test_user"
        external_user_id = "987654321"
        submission_source = ContentQueueSubmissionSource.Twitch
        submission_source_id = 1
        
        mock_handler = MagicMock()
        mock_handler.fetch_data = AsyncMock(return_value = ContentDict(
            url=url,
            deduplicated_url=mock_platform_data['deduplicated_url'],
            title=mock_platform_data['title'],
            duration=mock_platform_data['duration'],
            thumbnail_url=mock_platform_data['thumbnail_url'],
            channel_name=mock_platform_data['channel_name'],
            author=mock_platform_data['author'],
            created_at=mock_platform_data['created_at']
        ))
        mock_fetch_data.return_value = mock_handler

        # Mock session query results for the add_to_content_queue function
        mock_session.execute.return_value.scalars.return_value.one_or_none.side_effect = [
            ContentQueueSettings(broadcaster_id=broadcaster_id, allowed_platforms=""),
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
    async def test_add_to_content_queue_existing_content(self, mock_fetch_data, mock_session):
        """Test adding existing content to the queue"""
        # Setup mocks
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        broadcaster_id = 123456789
        username = "test_user"
        external_user_id = "987654321"
        submission_source = ContentQueueSubmissionSource.Twitch
        submission_source_id = 1
        
        
        # Mock existing content and queue item
        existing_content = MagicMock(spec=Content)
        existing_content.id = 42
        existing_content.stripped_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        
        existing_user = MagicMock(spec=ExternalUser)
        existing_user.id = 24
        
        existing_weight = MagicMock(spec=ExternalUserWeight)
        existing_weight.id = 12
        existing_weight.banned = False
        
        existing_queue_item = None  # Content exists but not in queue
        
        # Mock session query results
        mock_session.execute.return_value.scalars.return_value.one_or_none.side_effect = [
            ContentQueueSettings(broadcaster_id=broadcaster_id, allowed_platforms=""),
            existing_content,  # Content exists
            existing_user,  # External user exists
            existing_weight,  # External user weight exists
            existing_queue_item,  # Not in queue yet
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
        mock_fetch_data.assert_not_called()  # Should not fetch data for existing content
        
        # Check that a new queue item was created
        queue_add_call = mock_session.add.call_args_list[0]
        queue_item = queue_add_call[0][0]
        assert isinstance(queue_item, ContentQueue)
        assert queue_item.content_id == existing_content.id
        assert queue_item.broadcaster_id == broadcaster_id
        

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
        mock_session.add.assert_not_called()  # Nothing should be added
        mock_session.commit.assert_not_called()  # No database changes

    @pytest.mark.asyncio
    @patch('bot.shared.get_platform')
    async def test_add_to_content_queue_disallowed_platform(self, mock_fetch_data, mock_session):
        """Test adding existing content to the queue"""
        # Setup mocks
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        broadcaster_id = 123456789
        username = "test_user"
        external_user_id = "987654321"
        submission_source = ContentQueueSubmissionSource.Twitch
        submission_source_id = 1
        
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
            ContentQueueSettings(broadcaster_id=broadcaster_id, allowed_platforms="twitch"),
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
        mock_fetch_data.assert_not_called()  # Should not fetch data
        mock_session.add.assert_not_called()  # Nothing should be added
        mock_session.commit.assert_not_called()  # No database changes