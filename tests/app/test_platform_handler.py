import pytest
from app.platforms.handler import PlatformRegistry


class TestPlatformHandlerDetection:
    """Tests for the platform handler"""
    @pytest.mark.parametrize("url,expected", [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube_video"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=123", "youtube_video"),
        ("https://youtube.com/watch?v=dQw4w9WgXcQ&t=123", "youtube_video"),
        ("https://youtu.be/dQw4w9WgXcQ", "youtube_video"),
        ('https://youtu.be/dQw4w9WgXcQ?feature=shared&t=44', "youtube_video"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "youtube_short"),
        ("https://www.youtube.com/clip/UgkxFyeXQtfPRff43kUWbsAeuBND6Lb4ysEM", "youtube_clip"),
        ("https://twitch.tv/videos/123456789?t=1h2m3s", "twitch_video"),
        ("https://twitch.tv/videos/123456789?t=2m3s", "twitch_video"),
        ("https://twitch.tv/videos/123456789", "twitch_video"),
        ("https://clips.twitch.tv/CleverClipName", "twitch_clip"),
        ("https://twitch.tv/broadcaster/clip/CleverClipName", "twitch_clip"),
        ("https://clips.twitch.tv/IronicArtisticOrcaWTRuck-UecXBrM6ECC-DAZR", "twitch_clip"),
        ("https://www.twitch.tv/henlips1/clip/HeartlessTenderTardigradeUWot-yBpsR8gmD3IuNTIt?filter=clips&range=all&sort=time", "twitch_clip"),
    ])
    def test_get_platform_by_url(self, url, expected):
        """Test that platforms are correctly identified from URLs"""
        assert PlatformRegistry.get_handler_by_url(url).handler_name == expected

    @pytest.mark.parametrize("url", [
        'https://www.twitch.tv/my_supreme_streamer',
        "https://example.com",
        'https://www.youtube.com/@RickAstleyYT',
        "not a url",
    ])
    def test_get_platform_by_url_invalid(self, url):
        """Test that platforms are correctly identified from URLs"""
        with pytest.raises(ValueError):
            PlatformRegistry.get_handler_by_url(url)


class TestPlatformHandlerUrlUtilities:
    """Tests for the platform handler url utilities"""
    @pytest.mark.parametrize("url, seconds_offset, expected", [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", 123, "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=123"),
        ("https://youtu.be/dQw4w9WgXcQ", 123, "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=123"),
        ("https://www.twitch.tv/videos/123456789", 123, "https://www.twitch.tv/videos/123456789?t=02m03s"),
        ("https://www.twitch.tv/videos/123456789", 3753, "https://www.twitch.tv/videos/123456789?t=01h02m33s"),
    ])
    def test_get_url_with_timestamp(self, url, seconds_offset, expected):
        """Test that we get the correct url with timestamp"""
        assert PlatformRegistry.get_url_with_timestamp(url, seconds_offset) == expected
        
    @pytest.mark.parametrize("url, seconds_offset", [
        ("https://wubadib.com/watch?v=dQw4w9WgXcQ", 123),
        ("https://www.twitch.tv/videos/123456789", -123),
        ("https://www.twitch.tv/videos/123456789", 0),
        ("https://clips.twitch.tv/CleverClipName", 123),
        ("https://youtube.com/shorts/dQw4w9WgXcQ", 123),
    ])
    def test_get_url_with_timestamp_invalid(self, url, seconds_offset):
        """Test that we get the correct url with timestamp"""
        with pytest.raises(ValueError):
            PlatformRegistry.get_url_with_timestamp(url, seconds_offset)

    @pytest.mark.parametrize("url, expected", [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        ("https://www.twitch.tv/videos/123456789", "https://www.twitch.tv/videos/123456789"),
        ("https://clips.twitch.tv/CleverClipName", "https://clips.twitch.tv/CleverClipName"),
        ("https://twitch.tv/broadcaster/clip/CleverClipName", "https://clips.twitch.tv/CleverClipName"),
        ("https://youtube.com/shorts/dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        ("https://www.twitch.tv/henlips1/clip/HeartlessTenderTardigradeUWot-yBpsR8gmD3IuNTIt?filter=clips&range=all&sort=time", "https://clips.twitch.tv/HeartlessTenderTardigradeUWot-yBpsR8gmD3IuNTIt"),
    ])
    def test_deduplicate_url(self, url, expected):
        """Test that we get the correct deduplicated url"""
        assert PlatformRegistry.get_handler_by_url(url).deduplicate_url() == expected

    
    @pytest.mark.parametrize("url, expected", [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=123", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?t=123", "https://youtu.be/dQw4w9WgXcQ"),
        ("https://www.twitch.tv/videos/123456789?t=1h2m3s", "https://www.twitch.tv/videos/123456789"),
        ("https://clips.twitch.tv/CleverClipName", "https://clips.twitch.tv/CleverClipName"),
        ("https://twitch.tv/broadcaster/clip/CleverClipName", "https://twitch.tv/broadcaster/clip/CleverClipName"),
        ("https://youtube.com/shorts/dQw4w9WgXcQ?t=123", "https://youtube.com/shorts/dQw4w9WgXcQ"),
        ("https://www.twitch.tv/henlips1/clip/HeartlessTenderTardigradeUWot-yBpsR8gmD3IuNTIt?filter=clips&range=all&sort=time", "https://www.twitch.tv/henlips1/clip/HeartlessTenderTardigradeUWot-yBpsR8gmD3IuNTIt"),
    ])
    def test_sanitize_url(self, url, expected):
        """Test that we get the correct sanitized url"""
        assert PlatformRegistry.get_handler_by_url(url).sanitize_url() == expected