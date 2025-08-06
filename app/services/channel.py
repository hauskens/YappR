"""
Channel service for handling channel-related business logic.
"""
import asyncio
from collections.abc import Sequence
from typing import Optional

from sqlalchemy import select, func
from app.models import db
from app.models import (
    Video, Platforms, Broadcaster, Channels, Transcription, ChannelModerator,
    ChannelSettings, ContentQueue, ContentQueueSubmission, ChatLog, ChannelCreate,
    TranscriptionSource
)
from app.logger import logger
from app.utils import save_generic_thumbnail


class ChannelService:
    """Service class for channel-related operations."""

    @staticmethod
    def get_by_id(channel_id: int) -> Channels:
        """Get channel by ID."""
        return db.session.execute(
            select(Channels).filter_by(id=channel_id)
        ).scalars().one()

    @staticmethod
    def get_by_platform_ref(platform_ref: str) -> Channels | None:
        """Get channel by platform reference."""
        return db.session.execute(
            select(Channels).filter_by(platform_ref=platform_ref)
        ).scalars().one_or_none()

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
            .filter(Channels.platform_name.ilike("twitch"))
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
        from .platform import PlatformServiceRegistry

        platform_service = PlatformServiceRegistry.get_service_for_channel(
            channel)
        if platform_service:
            return platform_service.get_channel_url(channel.platform_ref)

        raise ValueError(f"Could not generate url for channel: {channel.id}")

    @staticmethod
    def update_channel_details(channel: Channels):
        """Update channel details from platform APIs."""
        from .platform import PlatformServiceRegistry
        platform_service = PlatformServiceRegistry.get_service_for_channel(
            channel)
        if platform_service:
            details = asyncio.run(
                platform_service.fetch_channel_details(channel.platform_ref))
            channel.platform_channel_id = details.platform_ref
            db.session.commit()
            return

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
            db.session.query(ChannelSettings).filter_by(
                channel_id=channel_id).delete()

            # Delete channel moderators
            db.session.query(ChannelModerator).filter_by(
                channel_id=channel_id).delete()

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
            logger.warning(
                f"Channel {channel.name} has no source channel for linking")
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

    # TODO: implement
    # @staticmethod
    # def fetch_videos_all(channel: Channels):
    #     """Fetch all videos from platform (YouTube only)."""
    #     if channel.platform.name.lower() == "youtube" and channel.platform_channel_id is not None:
    #         from .video import VideoService
    #         logger.info(
    #             f"Fetching all videos for YouTube channel {channel.name}")
    #         all_videos = get_all_videos_on_channel(channel.platform_channel_id)
    #         video_id_set = set()
    #         for search_result in all_videos:
    #             video_ref = search_result.id.videoId
    #             logger.debug("Checking if video is already in database", extra={
    #                          "video_ref": video_ref})
    #             existing_video = VideoService.get_by_platform_ref(video_ref)
    #             if existing_video is None:
    #                 video_id_set.add(video_ref)
    #         if len(video_id_set) > 0:
    #             videos = get_videos(list(video_id_set))
    #             for video in videos:
    #                 thumbnail_url = get_youtube_thumbnail_url(video)
    #                 video_create = VideoCreate(
    #                     title=video.snippet.title,
    #                     video_type=VideoType(channel.main_video_type),
    #                     duration=video.contentDetails.duration.total_seconds(),
    #                     channel_id=channel.id,
    #                     platform_ref=video_ref,
    #                     uploaded=video.snippet.publishedAt,
    #                     active=True,
    #                     thumbnail_url=thumbnail_url
    #                 )
    #                 VideoService.create(video_create)
    #         else:
    #             logger.info("No new videos found")

    @staticmethod
    def fetch_latest_videos(channel: Channels, force: bool = False):
        """Fetch latest videos from platform."""
        from .platform import PlatformServiceRegistry
        from .video import VideoService
        platform_service = PlatformServiceRegistry.get_service_for_channel(
            channel)
        if platform_service is None:
            logger.error(f"Platform {channel.platform_name} not found")
            return None

        videos = asyncio.run(platform_service.fetch_latest_videos(channel))
        if videos is None:
            logger.error(
                f"Failed to fetch latest videos for channel {channel.name}")
            return None

        for video in videos:
            existing_video = VideoService.get_by_platform_ref(
                video.platform_ref)
            if existing_video is None:
                VideoService.create(video)
            else:
                if force:
                    thumbnail = save_generic_thumbnail(video.thumbnail_url)
                    existing_video.thumbnail = open(
                        thumbnail, "rb")  # type: ignore[assignment]
                existing_video.title = video.title
                existing_video.video_type = video.video_type
                existing_video.duration = video.duration
                existing_video.uploaded = video.uploaded
                existing_video.active = video.active
                existing_video.source_video_id = video.source_video_id

        db.session.commit()

    @staticmethod
    def create(channel_create: ChannelCreate) -> Channels:
        """Create a new channel."""
        channel = Channels(
            name=channel_create.name,
            broadcaster_id=channel_create.broadcaster_id,
            platform_name=channel_create.platform_name.name,
            platform_ref=channel_create.platform_ref,
            platform_channel_id=channel_create.platform_channel_id,
            main_video_type=channel_create.main_video_type,
            source_channel_id=channel_create.source_channel_id
        )
        db.session.add(channel)
        db.session.commit()
        logger.info(f"Created channel: {channel.name}")
        return channel

    # TODO: Validate
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
