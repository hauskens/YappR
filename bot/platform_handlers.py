from abc import ABC, abstractmethod
import re
from typing import Dict, List, Pattern, Type, TypeVar
from datetime import datetime
from urllib.parse import urlparse, parse_qs

from app.twitch_api import get_twitch_video_id, get_twitch_video_by_ids, get_twitch_clips, parse_clip_id, parse_time, Twitch
from app.youtube_api import get_youtube_video_id, get_youtube_video_id_from_clip, get_videos, get_youtube_thumbnail_url
from app.logger import logger
from typing import TypedDict

T = TypeVar('T', bound='PlatformHandler')

class ContentDict(TypedDict):
    """TypedDict representing content stored in memory"""
    url: str
    sanitized_url: str
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
    
    # URL pattern to match for this platform
    url_pattern: Pattern[str]
    
    @classmethod
    def matches_url(cls, url: str) -> bool:
        """Check if the URL matches this platform's pattern"""
        return bool(cls.url_pattern.match(url))
    
    @abstractmethod
    def sanitize_url(self, url: str) -> str:
        """Sanitize a URL for this platform"""
        pass
    
    @abstractmethod
    async def fetch_data(self, url: str, **kwargs) -> ContentDict:
        """Fetch content data for a URL from this platform"""
        pass


class YouTubeHandler(PlatformHandler):
    """Handler for YouTube videos"""
    platform_name = "youtube"
    url_pattern = re.compile(r'^https?://(?:www\.)?(youtube\.com/watch\?v=|youtu\.be/)[\w\-]{11}')
    
    def sanitize_url(self, url: str) -> str:
        """Sanitize a YouTube URL by removing query parameters except video ID"""
        parsed_url = urlparse(url)
        
        query_params = parse_qs(parsed_url.query)
        if parsed_url.hostname in ["youtu.be"]:
            return f"https://www.youtube.com/watch?v={parsed_url.path.lstrip('/')}"
        
        if 'v' in query_params:
            video_id = query_params['v'][0]
            return f"https://www.youtube.com/watch?v={video_id}"
            
        raise ValueError("URL is not a YouTube URL")
    
    async def fetch_data(self, url: str, **kwargs) -> ContentDict:
        """Fetch video data from YouTube"""
        try:
            logger.info(f"Fetching YouTube data for url: {url}")
            thumbnail_url = get_youtube_thumbnail_url(url)
            video_id = get_youtube_video_id(url)
            video_details = get_videos([video_id])[0]
            
            return ContentDict(
                url=url,
                sanitized_url=self.sanitize_url(url),
                title=video_details.snippet.title,
                duration=int(video_details.contentDetails.duration.total_seconds()),
                thumbnail_url=thumbnail_url,
                channel_name=video_details.snippet.channelTitle,
                created_at=video_details.snippet.publishedAt,
                author=None
            )
        except Exception as e:
            logger.error(f"Failed to fetch YouTube data for url: {url}, exception: {e}")
            raise ValueError("Failed to fetch YouTube data")


class YouTubeShortHandler(YouTubeHandler):
    """Handler for YouTube shorts"""
    platform_name = "youtube_short"
    url_pattern = re.compile(r'^https?://(?:www\.)?(youtube\.com/shorts/)[\w\-]{11}')
    
    def sanitize_url(self, url: str) -> str:
        """Sanitize a YouTube Shorts URL by converting to standard watch URL"""
        parsed_url = urlparse(url)
        
        if 'shorts' in parsed_url.path:
            return f"https://www.youtube.com/watch?v={parsed_url.path.split('/')[-1]}"
            
        raise ValueError("URL is not a YouTube Shorts URL")


class YouTubeClipHandler(PlatformHandler):
    """Handler for YouTube clips"""
    platform_name = "youtube_clip"
    url_pattern = re.compile(r'^https?://(?:www\.)?(youtube\.com/clip/)[\w\-]{36}')
    
    def sanitize_url(self, url: str) -> str:
        """Sanitize a YouTube Clip URL"""
        parsed_url = urlparse(url)
        return f"https://{parsed_url.hostname}{parsed_url.path}"
    
    async def fetch_data(self, url: str, **kwargs) -> ContentDict:
        """Fetches video data from YouTube clip"""
        try:
            logger.info(f"Fetching YouTube clip data for url: {url}")
            video_id = get_youtube_video_id_from_clip(url)
            original_url = f"https://www.youtube.com/watch?v={video_id}"
            thumbnail_url = get_youtube_thumbnail_url(original_url)
            
            if video_id is None:
                logger.error(f"Failed to fetch YouTube clip data for url: {url}")
                raise ValueError("Failed to fetch YouTube clip data")
                
            video_details = get_videos([video_id])[0]
            
            return ContentDict(
                url=url,
                sanitized_url=self.sanitize_url(url),
                title=video_details.snippet.title,
                duration=int(video_details.contentDetails.duration.total_seconds()),
                thumbnail_url=thumbnail_url,
                channel_name=video_details.snippet.channelTitle,
                created_at=video_details.snippet.publishedAt,
                author=None
            )
        except Exception as e:
            logger.error(f"Failed to fetch YouTube clip data for url: {url}, exception: {e}")
            raise ValueError("Failed to fetch YouTube clip data")


class TwitchVideoHandler(PlatformHandler):
    """Handler for Twitch videos"""
    platform_name = "twitch_video"
    url_pattern = re.compile(r'^https?://(?:www\.)?twitch\.tv/videos/\d+\?t=\d+h\d+m\d+s')
    
    def sanitize_url(self, url: str) -> str:
        """Sanitize a Twitch Video URL"""
        parsed_url = urlparse(url)
        return f"https://www.twitch.tv/videos/{parsed_url.path.split('/')[-1]}"
    
    async def fetch_data(self, url: str, **kwargs) -> ContentDict:
        """Fetches video data from Twitch"""
        try:
            twitch = kwargs.get('twitch')
            if twitch is None:
                raise ValueError("Twitch client is required to fetch Twitch data")
                
            logger.info(f"Fetching Twitch data for url: {url}")
            video_id = get_twitch_video_id(url)
            video_details = await get_twitch_video_by_ids([video_id], api_client=twitch)
            video = video_details[0]
            
            return ContentDict(
                url=url,
                sanitized_url=self.sanitize_url(url),
                title=video.title,
                duration=parse_time(video.duration),
                thumbnail_url=video.thumbnail_url,
                channel_name=video.user_name,
                created_at=video.created_at,
                author=None
            )
        except Exception as e:
            logger.error(f"Failed to fetch Twitch data for url: {url}, exception: {e}")
            raise ValueError("Failed to fetch Twitch data")


class TwitchClipHandler(PlatformHandler):
    """Handler for Twitch clips"""
    platform_name = "twitch_clip"
    url_pattern = re.compile(r'^https?://(?:clips\.twitch\.tv/[\w\-]+|(?:www\.)?twitch\.tv/\w+/clip/[\w\-]+)')
    
    def sanitize_url(self, url: str) -> str:
        """Sanitize a Twitch Clip URL"""
        parsed_url = urlparse(url)
        
        if parsed_url.path.find("/clip/") != -1:
            return f"https://clips.twitch.tv/{parsed_url.path.split('/')[-1]}"
            
        return f"https://clips.twitch.tv/{parsed_url.path.split('/')[-1]}"
    
    async def fetch_data(self, url: str, **kwargs) -> ContentDict:
        """Fetches clip data from Twitch"""
        try:
            twitch = kwargs.get('twitch')
            if twitch is None:
                raise ValueError("Twitch client is required to fetch Twitch data")
                
            logger.info(f"Fetching Twitch data for clip url: {url}")
            clip_id = parse_clip_id(url)
            clip_details = await get_twitch_clips([clip_id], api_client=twitch)
            clip = clip_details[0]
            
            return ContentDict(
                url=url,
                sanitized_url=self.sanitize_url(url),
                title=clip.title,
                duration=int(clip.duration),
                thumbnail_url=clip.thumbnail_url,
                channel_name=clip.broadcaster_name,
                created_at=clip.created_at,
                author=clip.creator_name
            )
        except Exception as e:
            logger.error(f"Failed to fetch Twitch data for url: {url}, exception: {e}")
            raise ValueError("Failed to fetch Twitch data")


class PlatformRegistry:
    """Registry for platform handlers"""
    _handlers: Dict[str, Type[PlatformHandler]] = {}
    
    @classmethod
    def register(cls, handler_class: Type[PlatformHandler]) -> None:
        """Register a platform handler"""
        cls._handlers[handler_class.platform_name] = handler_class
    
    @classmethod
    def get_handler_for_url(cls, url: str) -> PlatformHandler:
        """Get the appropriate handler for a URL"""
        for handler_class in cls._handlers.values():
            if handler_class.matches_url(url):
                return handler_class()
        raise ValueError(f"Unsupported URL: {url}")
    
    @classmethod
    def get_handler_by_platform(cls, platform: str) -> PlatformHandler:
        """Get a handler by platform name"""
        if platform in cls._handlers:
            return cls._handlers[platform]()
        raise ValueError(f"Unsupported platform: {platform}")
    
    @classmethod
    def get_platform_name(cls, url: str) -> str:
        """Get the platform name for a URL"""
        for handler_class in cls._handlers.values():
            if handler_class.matches_url(url):
                return handler_class.platform_name
        return None


# Register all platform handlers
PlatformRegistry.register(YouTubeHandler)
PlatformRegistry.register(YouTubeShortHandler)
PlatformRegistry.register(YouTubeClipHandler)
PlatformRegistry.register(TwitchVideoHandler)
PlatformRegistry.register(TwitchClipHandler)
