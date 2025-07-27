"""Tests for ChannelService."""
import pytest
from unittest.mock import Mock, patch
from app.services import ChannelService
from datetime import datetime

@pytest.fixture
def platforms():
    youtube = Mock()
    youtube.name = "YouTube"
    youtube.url = "https://youtube.com"
    twitch = Mock()
    twitch.name = "Twitch"
    twitch.url = "https://twitch.tv"
    return {"YouTube": youtube, "Twitch": twitch}

@pytest.fixture
def channel():
    channel = Mock()
    channel.platform = Mock()
    channel.platform_ref = "testchannel"
    return channel

@pytest.fixture
def video():
    video = Mock()
    video.uploaded = datetime(2023, 1, 1)
    return video

@pytest.fixture
def videos():
    videos = [Mock(), Mock(), Mock()]
    videos[0].uploaded = datetime(2023, 1, 1)
    videos[1].uploaded = datetime(2023, 1, 2)
    videos[2].uploaded = datetime(2023, 1, 3)
    return videos

class TestChannelServiceUnit:
    @pytest.mark.parametrize("platform, expected", [
        ("YouTube", "https://youtube.com/@testchannel"),
        ("Twitch", "https://twitch.tv/testchannel"),
    ])
    @pytest.mark.unit
    def test_get_url_logic(self, platforms, channel, platform, expected):
        """Test URL generation logic for channels. It should return the correct URL based on the platform and platform_ref."""
        
        platform = platforms[platform]
        channel.platform = platform
        
        result = ChannelService.get_url(channel)
        assert result == expected
    
    @pytest.mark.unit
    def test_get_url_unsupported_platform_logic(self):
        """Test URL generation logic for unsupported platforms raises ValueError."""
        
        platform = Mock()
        platform.name = "UnsupportedPlatform"
        platform.url = "https://example.com"
        
        channel.platform = platform
        channel.platform_ref = "testuser"
        channel.id = 123
        
        with pytest.raises(ValueError):
            ChannelService.get_url(channel)
    
    @pytest.mark.unit
    def test_get_videos_sorted_by_uploaded_logic(self, channel, videos):
        """Test sorting videos by upload date logic."""
        
        channel.videos = videos  # Unordered
        
        # Test descending (default)
        result = ChannelService.get_videos_sorted_by_uploaded(channel)
        assert result == [videos[2], videos[1], videos[0]]
        
        # Test ascending
        result = ChannelService.get_videos_sorted_by_uploaded(channel, descending=False)
        assert result == [videos[0], videos[1], videos[2]]
    