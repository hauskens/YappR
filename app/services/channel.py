"""
Channel service for handling channel-related business logic.
"""
import asyncio
from collections.abc import Sequence
from typing import Optional

from sqlalchemy import select, func
from app.models import db
from app.models import Video, Platforms, Broadcaster, Channels, Transcription, ChannelModerator, ChannelSettings, ContentQueue, ContentQueueSubmission, ChatLog, TranscriptionSource
from app.logger import logger
from app.youtube_api import get_youtube_channel_details
from app.twitch_api import get_twitch_user


class ChannelService:
    """Service class for channel-related operations."""
    
    @staticmethod
    def get_by_id(channel_id: int) -> Channels:
        """Get channel by ID."""
        return db.session.execute(
            select(Channels).filter_by(id=channel_id)
        ).scalars().one()

    @staticmethod
    def get_all(show_hidden: bool = False) -> Sequence[Channels]:
        """Get all channels, optionally including hidden ones."""
        query = select(Channels)
        if not show_hidden:
            query = query.join(Broadcaster).filter(Broadcaster.hidden == False)
        query = query.order_by(Channels.id)
        return db.session.execute(query).scalars().all()
    
    @staticmethod
    def get_videos_by_channel(channel_id: int) -> Sequence[Video]:
        """Get all videos for a channel, ordered by upload date."""
        return db.session.execute(
            select(Video)
            .filter_by(channel_id=channel_id)
            .order_by(Video.uploaded.desc())
        ).scalars().all()
    
    @staticmethod
    def get_all_twitch_channels() -> Sequence[Channels]:
        """Get all Twitch channels."""
        return db.session.execute(
            select(Channels)
            .join(Platforms)
            .filter(Platforms.name.ilike("twitch"))
            .order_by(Channels.name)
        ).scalars().all()
    
    @staticmethod
    def get_stats_videos_with_audio(channel_id: int) -> int:
        """Get count of videos with audio for a channel."""
        return (
            db.session.query(func.count(func.distinct(Video.id)))
            .filter(Video.audio.is_not(None), Video.channel_id == channel_id)
            .scalar() or 0
        )
    
    @staticmethod
    def get_stats_videos_with_good_transcription(channel_id: int) -> int:
        """Get count of videos with high quality transcriptions for a channel."""
        return (
            db.session.query(func.count(func.distinct(Video.id)))
            .filter(
                Video.transcriptions.any(
                    Transcription.source == TranscriptionSource.Unknown
                ),
                Video.channel_id == channel_id,
            )
            .scalar() or 0
        )
    
    @staticmethod
    def get_moderated_channels(user_id: int) -> list[ChannelModerator]:
        """Get channels moderated by a user."""
        return db.session.query(ChannelModerator).filter_by(user_id=user_id).all()
    
    @staticmethod
    def get_url(channel: Channels) -> str:
        """Get the URL for a channel based on its platform."""
        url = channel.platform.url
        if channel.platform.name.lower() == "youtube":
            return f"{url}/@{channel.platform_ref}"
        elif channel.platform.name.lower() == "twitch":
            return f"{url}/{channel.platform_ref}"
        raise ValueError(f"Could not generate url for channel: {channel.id}")
    
    @staticmethod
    def update_channel_details(channel: Channels):
        """Update channel details from platform APIs."""
        # TODO: Add platform class
        if channel.platform.name.lower() == "youtube":
            channel.platform_channel_id = get_youtube_channel_details(channel.platform_ref).id
        elif channel.platform.name.lower() == "twitch":
            channel.platform_channel_id = asyncio.run(get_twitch_user(channel.platform_ref)).id
        db.session.commit()
        
    
    @staticmethod
    def link_to_channel(channel: Channels, target_channel_id: Optional[int] = None):
        """Link channel to another channel or unlink if None."""
        if target_channel_id is not None:
            try:
                target_channel = (
                    db.session.query(Channels)
                    .filter_by(id=target_channel_id, broadcaster_id=channel.broadcaster_id)
                    .one()
                )
                channel.source_channel_id = target_channel.id
                db.session.commit()
            except Exception:
                raise ValueError(
                    "Failed to find target channel on broadcaster, is the broadcaster the same?"
                )
        else:
            channel.source_channel_id = None
            db.session.commit()
    
    @staticmethod
    def delete_channel(channel_id: int) -> bool:
        """Delete a channel and all associated data."""
        try:
            channel = ChannelService.get_by_id(channel_id)
            
            # Delete associated videos (cascade will handle transcriptions/segments)
            from .video import VideoService
            for video in channel.videos:
                VideoService.delete_video(video)
            
            # Delete chat logs
            db.session.query(ChatLog).filter_by(channel_id=channel_id).delete()
            
            # Delete channel settings
            db.session.query(ChannelSettings).filter_by(channel_id=channel_id).delete()
            
            # Delete channel moderators
            db.session.query(ChannelModerator).filter_by(channel_id=channel_id).delete()
            
            # Delete content queue items if broadcaster exists
            if channel.broadcaster_id is not None:
                queue = db.session.query(ContentQueue).filter_by(
                    broadcaster_id=channel.broadcaster_id
                ).all()
                for q_item in queue:
                    db.session.query(ContentQueueSubmission).filter_by(
                        content_queue_id=q_item.id
                    ).delete()
                db.session.query(ContentQueue).filter_by(
                    broadcaster_id=channel.broadcaster_id
                ).delete()
            
            # Delete the channel
            db.session.query(Channels).filter_by(id=channel_id).delete()
            db.session.commit()
            
            logger.info(f"Deleted channel {channel_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete channel {channel_id}: {e}")
            db.session.rollback()
            return False
    
    @staticmethod
    def update_thumbnails(channel: Channels):
        """Update thumbnails for all videos in the channel."""
        from .video import VideoService
        for video in channel.videos:
            if video.thumbnail is None:
                VideoService.fetch_details(video, force=True)
    
    @staticmethod
    def process_videos(channel: Channels, force: bool = False):
        """Process transcriptions for all videos in the channel."""
        from .video import VideoService
        for video in channel.videos:
            VideoService.process_transcriptions(video, force)
    
    @staticmethod
    def download_audio_videos(channel: Channels, force: bool = False):
        """Download audio for all videos in the channel."""
        from .video import VideoService
        for video in channel.videos:
            VideoService.save_audio(video, force)
    
    @staticmethod
    def get_videos_sorted_by_uploaded(channel: Channels, descending: bool = True) -> list[Video]:
        """Get videos sorted by upload date."""
        return sorted(channel.videos, key=lambda v: v.uploaded, reverse=descending)
    
    @staticmethod
    def get_videos_sorted_by_id(channel: Channels, descending: bool = True) -> list[Video]:
        """Get videos sorted by ID."""
        return sorted(channel.videos, key=lambda v: v.id, reverse=descending)
    
    @staticmethod
    def look_for_linked_videos(channel: Channels, margin_sec: int = 2, min_duration: int = 300):
        """Look for videos that should be linked based on duration matching."""
        if not channel.source_channel:
            logger.warning(f"Channel {channel.name} has no source channel for linking")
            return
            
        logger.info(f"Looking for potential links on channel {channel.name}")
        for source_video in channel.source_channel.videos:
            for target_video in channel.videos:
                if (
                    target_video.source_video_id is None
                    and target_video.duration > min_duration
                    and (
                        (source_video.duration - margin_sec)
                        <= target_video.duration
                        <= (source_video.duration + margin_sec)
                    )
                ):
                    logger.info(
                        f"Found a match on video duration! Source: {source_video.id} -> target: {target_video.id}"
                    )
                    target_video.source_video_id = source_video.id
                    db.session.flush()
        db.session.commit()
    
    @staticmethod
    def fetch_videos_all(channel: Channels):
        """Fetch all videos from platform (YouTube only)."""
        #if channel.platform.name.lower() != "youtube":
        # TODO: fix   
        
        # Note: This would need YouTube API integration
        # from app.services.youtube import get_all_videos_on_channel, get_videos, save_yt_thumbnail
        # latest_video_batches = get_all_videos_on_channel(channel.platform_channel_id)
        # ... implementation details would go here
        logger.info(f"Would fetch all videos for YouTube channel {channel.name}")
    
    @staticmethod
    def fetch_latest_videos(channel: Channels, process: bool = False) -> Optional[int]:
        """Fetch latest videos from platform."""
        if channel.platform.name.lower() == "youtube" and channel.platform_channel_id is not None:
            # Note: This would need YouTube API integration
            logger.info(f"Would fetch latest YouTube videos for channel {channel.name}")
            return None
        elif channel.platform.name.lower() == "twitch" and channel.platform_channel_id is not None:
            # Note: This would need Twitch API integration
            logger.info(f"Would fetch latest Twitch videos for channel {channel.name}")
            return None
        
        db.session.commit()
        return None
    
    @staticmethod
    def create(name: str, broadcaster_id: int, platform_id: int, platform_ref: str, 
               platform_channel_id: Optional[str] = None) -> Channels:
        """Create a new channel."""
        channel = Channels(
            name=name,
            broadcaster_id=broadcaster_id,
            platform_id=platform_id,
            platform_ref=platform_ref,
            platform_channel_id=platform_channel_id
        )
        db.session.add(channel)
        db.session.commit()
        logger.info(f"Created channel: {name}")
        return channel
    
    @staticmethod
    def update(channel_id: int, **kwargs) -> Channels:
        """Update channel fields."""
        channel = ChannelService.get_by_id(channel_id)
        for key, value in kwargs.items():
            if hasattr(channel, key):
                setattr(channel, key, value)
        db.session.commit()
        return channel


# For template accessibility, create simple function interfaces
def get_channel_service() -> ChannelService:
    """Get channel service instance for use in templates."""
    return ChannelService()
