"""
Platform service for handling platform-specific business logic.
"""
from abc import ABC, abstractmethod
from typing import Dict
from app.models import PlatformType, VideoType

from app.logger import logger
from app.models import Channels, VideoCreate, ChannelPlatformDetails, VideoDetails, Users
from app.models.enums import TwitchAccountType
from app.utils import get_youtube_thumbnail_url, get_twitch_thumbnail_url
from app.youtube_api import get_videos, get_all_videos_on_channel, get_youtube_channel_details
from app.twitch_api import get_twitch_video_by_ids, parse_time, get_moderated_channels, get_twitch_user_by_id
from app.twitch_client_factory import TwitchClientFactory


class PlatformService(ABC):
    """Base abstract class for platform-level services"""

    platform_name: PlatformType
    base_url: str
    primary_color: str
    secondary_color: str = "#FFFFFF"
    allowed_video_types: list[VideoType] = []

    @abstractmethod
    async def fetch_latest_videos(self, channel: Channels, limit: int = 5, **kwargs) -> list[VideoCreate]:
        """Fetch latest videos from platform for a channel"""
        pass

    @abstractmethod
    async def fetch_channel_details(self, channel_ref: str, **kwargs) -> ChannelPlatformDetails:
        """Fetch channel details from platform"""
        pass

    @abstractmethod
    def get_channel_url(self, channel_ref: str) -> str:
        """Generate channel URL for this platform"""
        pass

    @abstractmethod
    async def fetch_video_details(self, video_ref: str, **kwargs) -> VideoDetails:
        """Fetch video details from platform"""
        pass

    @abstractmethod
    async def fetch_moderated_channels(self, user: Users) -> list[Channels]:
        """Get moderated channels for a user on a platform"""
        pass


class YouTubePlatformService(PlatformService):
    """Platform service for YouTube operations"""

    platform_name = PlatformType.YouTube
    base_url = "https://youtube.com"
    primary_color = "#FF0000"
    allowed_video_types = [VideoType.VOD, VideoType.Clip, VideoType.Edit]

    async def fetch_latest_videos(self, channel: Channels, limit: int = 5, **kwargs) -> list[VideoCreate]:
        """Fetch latest videos from YouTube channel"""
        try:
            logger.info(
                f"Fetching latest YouTube videos for channel {channel.name}")
            search_results = get_all_videos_on_channel(
                channel.platform_channel_id)

            if not search_results:
                return []

            # Get video IDs and fetch details
            sorted_results = sorted(
                search_results, key=lambda result: result.snippet.publishedAt, reverse=True)
            video_ids = [
                result.id.videoId for result in sorted_results[:limit]]
            
            # Process videos in batches of 100 (YouTube API limit)
            result: list[VideoCreate] = []
            batch_size = 100
            for i in range(0, len(video_ids), batch_size):
                batch_ids = video_ids[i:i + batch_size]
                videos = get_videos(batch_ids)
                
                for video in videos:
                    thumbnail_url = get_youtube_thumbnail_url(video.id)

                    content = VideoCreate(
                        title=video.snippet.title,
                        video_type=VideoType.VOD,
                        duration=int(
                            video.contentDetails.duration.total_seconds()),
                        thumbnail_url=thumbnail_url,
                        channel_id=channel.id,
                        platform_ref=video.id,
                        uploaded=video.snippet.publishedAt,
                        active=True
                    )
                    result.append(content)

            return result
        except Exception as e:
            logger.error(f"Failed to fetch latest YouTube videos: {e}")
            return []

    async def fetch_channel_details(self, channel_ref: str, **kwargs) -> ChannelPlatformDetails:
        """Fetch YouTube channel details"""
        try:
            logger.info(f"Fetching YouTube channel details for {channel_ref}")
            channel_details = get_youtube_channel_details(channel_ref)

            return ChannelPlatformDetails(
                platform_ref=channel_details.id
            )

        except Exception as e:
            logger.error(f"Failed to fetch YouTube channel details: {e}")
            raise ValueError(f"Failed to fetch YouTube channel details: {e}")

    async def fetch_video_details(self, video_ref: str, **kwargs) -> VideoDetails:
        try:

            logger.info(f"Fetching YouTube video details for {video_ref}")
            video = get_videos([video_ref])[0]

            return VideoDetails(
                platform_ref=video.id,
                title=video.snippet.title,
                video_type=VideoType.VOD,
                duration=video.contentDetails.duration.total_seconds(),
                uploaded=video.snippet.publishedAt,
                active=True,
                thumbnail_url=get_youtube_thumbnail_url(video.id)
            )
        except Exception as e:
            logger.error(f"Failed to fetch YouTube video details: {e}")
            raise ValueError(f"Failed to fetch YouTube video details: {e}")

    def get_channel_url(self, channel_ref: str) -> str:
        """Generate YouTube channel URL"""
        return f"{self.base_url}/@{channel_ref}"

    async def fetch_moderated_channels(self, user: Users) -> list[Channels]:
        return []


class TwitchPlatformService(PlatformService):
    """Platform service for Twitch operations"""

    platform_name = PlatformType.Twitch
    base_url = "https://twitch.tv"
    primary_color = "#6441a5"
    secondary_color = "#FFFFFF"
    allowed_video_types = [VideoType.VOD, VideoType.Clip]

    async def fetch_latest_videos(self, channel: Channels, limit: int = 5, **kwargs) -> list[VideoCreate]:
        """Fetch latest videos from Twitch channel"""
        try:
            from app.twitch_client_factory import TwitchClientFactory
            from app.twitch_api import get_latest_broadcasts, parse_time

            # Try to get client from kwargs, otherwise use appropriate client type
            twitch_client = kwargs.get('twitch')
            if not twitch_client:
                user_id = kwargs.get('user_id')
                if user_id:
                    twitch_client = await TwitchClientFactory.get_user_client(user_id)
                else:
                    twitch_client = await TwitchClientFactory.get_server_client()

            logger.info(
                f"Fetching latest Twitch videos for channel {channel.platform_channel_id}")
            
            # Process videos in batches of 100 (Twitch API limit)
            result: list[VideoCreate] = []
            batch_size = 100
            remaining_limit = limit
            
            while remaining_limit > 0:
                current_batch_size = min(batch_size, remaining_limit)
                videos = await get_latest_broadcasts(
                    channel.platform_channel_id, 
                    limit=current_batch_size, 
                    api_client=twitch_client
                )
                
                if not videos:
                    break
                    
                for video in videos:
                    thumbnail_url = get_twitch_thumbnail_url(video)
                    content = VideoCreate(
                        title=video.title,
                        video_type=VideoType.VOD,
                        duration=parse_time(video.duration),
                        thumbnail_url=thumbnail_url,
                        channel_id=channel.id,
                        platform_ref=video.id,
                        uploaded=video.created_at,
                        active=True
                    )
                    result.append(content)
                
                remaining_limit -= len(videos)
                
                # If we got fewer videos than requested, we've reached the end
                if len(videos) < current_batch_size:
                    break

            return result

        except Exception as e:
            logger.error(f"Failed to fetch latest Twitch videos: {e}")
            return []

    async def fetch_channel_details(self, channel_ref: str, **kwargs) -> ChannelPlatformDetails:
        """Fetch Twitch channel details"""
        try:
            from app.twitch_api import get_twitch_user

            # Try to get client from kwargs, otherwise use appropriate client type
            twitch_client = kwargs.get('twitch')
            if not twitch_client:
                user_id = kwargs.get('user_id')
                if user_id:
                    twitch_client = await TwitchClientFactory.get_user_client(user_id)
                else:
                    twitch_client = await TwitchClientFactory.get_server_client()

            logger.info(f"Fetching Twitch channel details for {channel_ref}")
            user_details = await get_twitch_user(channel_ref, api_client=twitch_client)

            return ChannelPlatformDetails(
                platform_ref=user_details.id
            )

        except Exception as e:
            logger.error(f"Failed to fetch Twitch channel details: {e}")
            raise ValueError(f"Failed to fetch Twitch channel details: {e}")

    def get_channel_url(self, channel_ref: str) -> str:
        """Generate Twitch channel URL"""
        return f"{self.base_url}/{channel_ref}"

    async def fetch_video_details(self, video_ref: str, **kwargs) -> VideoDetails:
        try:

            logger.info(f"Fetching Twitch video details for {video_ref}")
            video_result = await get_twitch_video_by_ids([video_ref])
            return VideoDetails(
                platform_ref=video_result[0].id,
                title=video_result[0].title,
                video_type=VideoType.VOD,
                duration=parse_time(video_result[0].duration),
                uploaded=video_result[0].created_at,
                active=True,
                thumbnail_url=get_twitch_thumbnail_url(video_result[0])
            )
        except Exception as e:
            logger.error(f"Failed to fetch Twitch video details: {e}")
            raise ValueError(f"Failed to fetch Twitch video details: {e}")

    async def fetch_moderated_channels(self, user: Users) -> list[Channels]:
        from .channel import ChannelService
        logger.info("Fetching moderated channels for %s", user.name)
        twitch_client = await TwitchClientFactory.get_user_client(user)
        moderated_channels = await get_moderated_channels(user.external_account_id, api_client=twitch_client)
        logger.info("Got twitch moderated channels for user id: %s - %s channels",
                     user.external_account_id, len(moderated_channels))
        result: list[Channels] = []
        for moderated_channel in moderated_channels:
            channel = ChannelService.get_by_platform_ref(
                moderated_channel.broadcaster_id)
            if channel is not None:
                result.append(channel)
        return result

    async def fetch_account_type(self, user: Users) -> TwitchAccountType:
        """Get account type for a user on Twitch, partner, affiliate or regular"""
        twitch_client = await TwitchClientFactory.get_user_client(user)
        twitch_user = await get_twitch_user_by_id(user.external_account_id, api_client=twitch_client)
        return TwitchAccountType(twitch_user.broadcaster_type.lower())


class PlatformServiceRegistry:
    """Registry for platform services"""
    _services: Dict[str, PlatformService] = {}

    @classmethod
    def register(cls, service: PlatformService) -> None:
        """Register a platform service"""
        cls._services[service.platform_name.value] = service

    @classmethod
    def get_service(cls, platform_name: PlatformType) -> PlatformService | None:
        """Get platform service by name"""
        return cls._services.get(platform_name.value)

    @classmethod
    def get_service_by_name(cls, name: str) -> PlatformService | None:
        """Get platform service by name"""
        return cls._services.get(name)

    @classmethod
    def get_service_for_channel(cls, channel: Channels) -> PlatformService | None:
        """Get platform service for a channel object"""
        platform_name = channel.platform_name
        return cls.get_service(PlatformType(platform_name))


# Register platform services
PlatformServiceRegistry.register(YouTubePlatformService())
PlatformServiceRegistry.register(TwitchPlatformService())
