from abc import ABC, abstractmethod
import re
from typing import Dict, Pattern, Type, TypeVar
from datetime import datetime
from urllib.parse import urlparse, parse_qs

from app.twitch_api import get_twitch_video_id, get_twitch_video_by_ids, get_twitch_clips, parse_clip_id, parse_time, Twitch
from app.youtube_api import get_youtube_video_id, get_youtube_video_id_from_clip, get_videos, get_youtube_thumbnail_url
from app.utils import get_youtube_url_with_timestamp, get_twitch_url_with_timestamp, get_timestamp_from_twitch_url, get_timestamp_from_youtube_url, get_youtube_video_id, get_twitch_video_id, get_twitch_clip_id
from app.logger import logger
from typing import TypedDict

T = TypeVar('T', bound='PlatformHandler')

class ContentDict(TypedDict):
    """TypedDict representing content stored in memory"""
    url: str
    deduplicated_url: str
    title: str
    duration: int
    thumbnail_url: str
    channel_name: str
    author: str | None
    created_at: datetime | None

class PlatformHandler(ABC):
    """Base abstract class for platform handlers"""
    
    # Platform name
    platform_name: str
    handler_name: str
    
    # URL pattern to match for this platform
    url_pattern: Pattern[str]

    seconds_offset: int | None = None
    url: str
    deduplicated_url: str

    def __init__(self, url: str):
        """Initialize the handler with an optional URL"""
        self.url = url
        self.deduplicated_url = self.deduplicate_url()
        self.seconds_offset = self.get_timestamp_from_url(self.url)

        if self.seconds_offset is not None and self.seconds_offset <= 0:
            raise ValueError("Timestamp must be positive")


    @classmethod
    def matches_url(cls, url: str) -> bool:
        """Check if the URL matches this platform's pattern"""
        return bool(cls.url_pattern.match(url))
    
    @abstractmethod
    def deduplicate_url(self) -> str:
        """Deduplicate a URL for this platform"""
        pass

    @abstractmethod
    def get_video_id_from_url(self) -> str:
        """Get the video ID from a URL"""
        pass
    
    def sanitize_url(self) -> str:
        """Sanitize a URL for this platform by removing unnecessary query parameters"""
        parsed_url = urlparse(self.url)
        query_params = parse_qs(parsed_url.query)
        if query_params.get('v'):
            return f"https://{parsed_url.hostname}{parsed_url.path}?v={query_params['v'][0]}"
        return f"https://{parsed_url.hostname}{parsed_url.path}"
    
    @abstractmethod
    async def fetch_data(self, **kwargs) -> ContentDict:
        """Fetch content data for a URL from this platform. 
        If url is provided, use that. Otherwise use the instance url."""
        pass

    @abstractmethod
    def get_url_with_timestamp(self, seconds_offset: float) -> str:
        """Generate a URL to the video at a specific timestamp."""
        pass

    @abstractmethod
    def get_timestamp_from_url(cls, url: str) -> int | None:
        """Get the timestamp from a URL"""
        pass

class YouTubeHandler(PlatformHandler):
    """Handler for YouTube videos"""
    platform_name = "youtube"
    handler_name = "youtube_video"
    url_pattern = re.compile(r'^https?://(?:www\.)?(youtube\.com/watch\?v=|youtu\.be/)[\w\-]{11}')

    def deduplicate_url(self) -> str:
        """Deduplicate a YouTube URL by removing query parameters except video ID"""
        parsed_url = urlparse(self.url)
        
        query_params = parse_qs(parsed_url.query)
        if parsed_url.hostname in ["youtu.be"]:
            return f"https://www.youtube.com/watch?v={parsed_url.path.lstrip('/')}"
        
        if 'v' in query_params:
            video_id = query_params['v'][0]
            return f"https://www.youtube.com/watch?v={video_id}"
            
        raise ValueError("URL is not a YouTube URL")
    
    async def fetch_data(self, **kwargs) -> ContentDict:
        """Fetch video data from YouTube"""
        try:
            logger.info(f"Fetching YouTube data for url: {self.url}")
            thumbnail_url = get_youtube_thumbnail_url(self.url)
            video_id = get_youtube_video_id(self.url)
            video_details = get_videos([video_id])[0]
            
            sanitized = self.deduplicate_url()
            return ContentDict(
                url=self.url,
                deduplicated_url=sanitized,
                title=video_details.snippet.title,
                duration=int(video_details.contentDetails.duration.total_seconds()),
                thumbnail_url=thumbnail_url,
                channel_name=video_details.snippet.channelTitle,
                created_at=video_details.snippet.publishedAt,
                author=None
            )
        except Exception as e:
            logger.error(f"Failed to fetch YouTube data for url: {self.url}, exception: {e}")
            raise ValueError("Failed to fetch YouTube data")

    def get_url_with_timestamp(self, seconds_offset: float) -> str:
        return get_youtube_url_with_timestamp(self.deduplicated_url, seconds_offset)

    def get_timestamp_from_url(self, url: str) -> int | None:
        return get_timestamp_from_youtube_url(url)

    def get_video_id_from_url(self) -> str:
        return get_youtube_video_id(self.url)

class YouTubeShortHandler(YouTubeHandler):
    """Handler for YouTube shorts"""
    platform_name = "youtube"
    handler_name = "youtube_short"
    url_pattern = re.compile(r'^https?://(?:www\.)?(youtube\.com/shorts/)[\w\-]{11}')
    
    def deduplicate_url(self) -> str:
        """Sanitize a YouTube Shorts URL by converting to standard watch URL"""
        parsed_url = urlparse(self.url)
        
        if 'shorts' in parsed_url.path:
            return f"https://www.youtube.com/watch?v={parsed_url.path.split('/')[-1]}"
            
        raise ValueError("URL is not a YouTube Shorts URL")

    async def fetch_data(self, **kwargs) -> ContentDict:
        """Fetch video data from YouTube"""
        try:
            logger.info(f"Fetching YouTube data for url: {self.url}")
            thumbnail_url = get_youtube_thumbnail_url(self.url)
            video_id = get_youtube_video_id(self.url)
            video_details = get_videos([video_id])[0]
            
            sanitized = self.deduplicate_url()
            return ContentDict(
                url=self.url,
                deduplicated_url=sanitized,
                title=video_details.snippet.title,
                duration=int(video_details.contentDetails.duration.total_seconds()),
                thumbnail_url=thumbnail_url,
                channel_name=video_details.snippet.channelTitle,
                created_at=video_details.snippet.publishedAt,
                author=None
            )
        except Exception as e:
            logger.error(f"Failed to fetch YouTube data for url: {self.url}, exception: {e}")
            raise ValueError("Failed to fetch YouTube data")

    def get_url_with_timestamp(self, seconds_offset: float) -> str:
        raise ValueError("YouTube Shorts do not support timestamps")

    def get_timestamp_from_url(self, url: str) -> int | None:
        return None

    def get_video_id_from_url(self) -> str:
        return get_youtube_video_id(self.url)

class YouTubeClipHandler(PlatformHandler):
    """Handler for YouTube clips"""
    platform_name = "youtube"
    handler_name = "youtube_clip"
    url_pattern = re.compile(r'^https?://(?:www\.)?(youtube\.com/clip/)[\w\-]{36}')
    
    def deduplicate_url(self) -> str:
        """Sanitize a YouTube Clip URL"""
        parsed_url = urlparse(self.url)
        return f"https://{parsed_url.hostname}{parsed_url.path}"
    
    async def fetch_data(self, **kwargs) -> ContentDict:
        """Fetches video data from YouTube clip"""
        try:
            logger.info(f"Fetching YouTube clip data for url: {self.url}")
            video_id = get_youtube_video_id_from_clip(self.url)
            original_url = f"https://www.youtube.com/watch?v={video_id}"
            thumbnail_url = get_youtube_thumbnail_url(original_url)
            
            if video_id is None:
                logger.error(f"Failed to fetch YouTube clip data for url: {self.url}")
                raise ValueError("Failed to fetch YouTube clip data")
                
            video_details = get_videos([video_id])[0]
            
            sanitized = self.deduplicate_url()
            return ContentDict(
                url=self.url,
                deduplicated_url=sanitized,
                title=video_details.snippet.title,
                duration=int(video_details.contentDetails.duration.total_seconds()),
                thumbnail_url=thumbnail_url,
                channel_name=video_details.snippet.channelTitle,
                created_at=video_details.snippet.publishedAt,
                author=None
            )
        except Exception as e:
            logger.error(f"Failed to fetch YouTube clip data for url: {self.url}, exception: {e}")
            raise ValueError("Failed to fetch YouTube clip data")

    def get_url_with_timestamp(self, seconds_offset: float) -> str:
        raise ValueError("YouTube clips do not support timestamps")

    def get_timestamp_from_url(self, url: str) -> int | None:
        return None

    def get_video_id_from_url(self) -> str:
        return get_youtube_video_id(self.url)

class TwitchVideoHandler(PlatformHandler):
    """Handler for Twitch videos"""
    platform_name = "twitch"
    handler_name = "twitch_video"
    url_pattern = re.compile(r'^https?://(?:www\.)?twitch\.tv/videos/\d+(?:\?t=\d+h\d+m\d+s)?')
    
    def deduplicate_url(self) -> str:
        """Sanitize a Twitch Video URL"""
        parsed_url = urlparse(self.url)
        return f"https://www.twitch.tv/videos/{parsed_url.path.split('/')[-1]}"
    
    async def fetch_data(self, **kwargs) -> ContentDict:
        """Fetches video data from Twitch"""
        try:
            target_url = self.url

            twitch = kwargs.get('twitch')
            if twitch is None:
                raise ValueError("Twitch client is required to fetch Twitch data")
                
            logger.info(f"Fetching Twitch data for url: {target_url}")
            video_id = get_twitch_video_id(target_url)
            video_details = await get_twitch_video_by_ids([video_id], api_client=twitch)
            video = video_details[0]
            
            sanitized = self.deduplicate_url()
            return ContentDict(
                url=self.url,
                deduplicated_url=sanitized,
                title=video.title,
                duration=parse_time(video.duration),
                thumbnail_url=video.thumbnail_url,
                channel_name=video.user_name,
                created_at=video.created_at,
                author=None
            )
        except Exception as e:
            logger.error(f"Failed to fetch Twitch data for url: {self.url}, exception: {e}")
            raise ValueError("Failed to fetch Twitch data")

    def get_url_with_timestamp(self, seconds_offset: float) -> str:
        return get_twitch_url_with_timestamp(self.deduplicated_url, seconds_offset)

    def get_timestamp_from_url(self, url: str) -> int | None:
        return get_timestamp_from_twitch_url(url)

    def get_video_id_from_url(self) -> str:
        return get_twitch_video_id(self.url)

class TwitchClipHandler(PlatformHandler):
    """Handler for Twitch clips"""
    platform_name = "twitch"
    handler_name = "twitch_clip"
    url_pattern = re.compile(r'^https?://(?:clips\.twitch\.tv/[\w\-]+|(?:www\.)?twitch\.tv/[^/]+/clip/[\w\-]+(?:-[\w\-]+)?)(?:\?.*)?$')
    
    def deduplicate_url(self) -> str:
        """Sanitize a Twitch Clip URL"""
        parsed_url = urlparse(self.url)
        
        if parsed_url.path.find("/clip/") != -1:
            return f"https://clips.twitch.tv/{parsed_url.path.split('/')[-1]}"
            
        return f"https://clips.twitch.tv/{parsed_url.path.split('/')[-1]}"
    
    async def fetch_data(self, **kwargs) -> ContentDict:
        """Fetches clip data from Twitch"""
        try:
            twitch = kwargs.get('twitch')
            if twitch is None:
                raise ValueError("Twitch client is required to fetch Twitch data")
                
            logger.info(f"Fetching Twitch data for clip url: {self.url}")
            clip_id = parse_clip_id(self.url)
            clip_details = await get_twitch_clips([clip_id], api_client=twitch)
            clip = clip_details[0]
            
            sanitized = self.deduplicate_url()
            return ContentDict(
                url=self.url,
                deduplicated_url=sanitized,
                title=clip.title,
                duration=int(clip.duration),
                thumbnail_url=clip.thumbnail_url,
                channel_name=clip.broadcaster_name,
                created_at=clip.created_at,
                author=clip.creator_name
            )
        except Exception as e:
            logger.error(f"Failed to fetch Twitch data for url: {self.url}, exception: {e}")
            raise ValueError("Failed to fetch Twitch data")

    def get_url_with_timestamp(self, seconds_offset: float) -> str:
        raise ValueError("Twitch clips do not support timestamps")

    def get_timestamp_from_url(self, url: str) -> int | None:
        return None

    def get_video_id_from_url(self) -> str:
        return get_twitch_clip_id(self.url)

class PlatformRegistry:
    """Registry for platform handlers"""
    _handlers: Dict[str, Type[PlatformHandler]] = {}
    
    @classmethod
    def register(cls, handler_class: Type[PlatformHandler]) -> None:
        """Register a platform handler"""
        cls._handlers[handler_class.handler_name] = handler_class
    
    @classmethod
    def get_handler_by_url(cls, url: str) -> PlatformHandler:
        """Get the appropriate handler for a URL"""
        for handler_class in cls._handlers.values():
            if handler_class.matches_url(url):
                return handler_class(url)
        raise ValueError(f"Unsupported URL: {url}")
    
    @classmethod
    def get_platform_name(cls, url: str) -> str:
        """Get the platform name for a URL"""
        for handler_class in cls._handlers.values():
            if handler_class.matches_url(url):
                return handler_class.handler_name
        raise ValueError(f"Unsupported URL: {url}")

    @classmethod
    def get_url_with_timestamp(cls, url: str, seconds_offset: float) -> str:
        """Generate a URL to the video at a specific timestamp."""
        handler = cls.get_handler_by_url(url)
        return handler.get_url_with_timestamp(seconds_offset)


# Register all platform handlers
PlatformRegistry.register(YouTubeHandler)
PlatformRegistry.register(YouTubeShortHandler)
PlatformRegistry.register(YouTubeClipHandler)
PlatformRegistry.register(TwitchVideoHandler)
PlatformRegistry.register(TwitchClipHandler)
