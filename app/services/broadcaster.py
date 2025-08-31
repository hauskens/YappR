"""
Broadcaster service for handling broadcaster-related business logic.
"""
from collections.abc import Sequence
from datetime import datetime
from sqlalchemy import select, func
from app.models import db
from app.models.broadcaster import Broadcaster, BroadcasterSettings
from app.models.channel import Channels
from app.models.video import Video
from app.models.transcription import Transcription
from app.models.enums import TranscriptionSource
from app.models.user import Users
from app.models.content_queue_settings import ContentQueueSettings
from app.logger import logger


class BroadcasterService:
    """Service class for broadcaster-related operations."""

    @staticmethod
    def get_all(show_hidden: bool = False) -> Sequence[Broadcaster]:
        """Get all broadcasters, optionally including hidden ones."""
        query = select(Broadcaster)
        if not show_hidden:
            query = query.filter_by(hidden=False)
        query = query.order_by(Broadcaster.id)
        return db.session.execute(query).scalars().all()

    @staticmethod
    def get_by_id(broadcaster_id: int) -> Broadcaster:
        """Get broadcaster by ID."""
        return db.session.execute(
            select(Broadcaster).filter_by(id=broadcaster_id)
        ).scalars().one()

    @staticmethod
    def get_by_external_id(external_id: str) -> Broadcaster | None:
        """Get broadcaster by external channel ID."""
        return db.session.execute(
            select(Broadcaster)
            .join(Broadcaster.channels)
            .where(Channels.platform_channel_id == external_id)
            .limit(1)
        ).scalars().one_or_none()
    
    @staticmethod
    def get_by_internal_channel_id(channel_id: int) -> Broadcaster | None:
        """Get broadcaster by internal channel ID."""
        return db.session.execute(
            select(Broadcaster)
            .join(Broadcaster.channels)
            .where(Channels.id == channel_id)
            .limit(1)
        ).scalars().one_or_none()

    @staticmethod
    def get_channels(broadcaster_id: int) -> Sequence[Channels]:
        """Get all channels for a broadcaster."""
        return db.session.execute(
            select(Channels).filter_by(broadcaster_id=broadcaster_id)
        ).scalars().all()

    @staticmethod
    def get_transcription_stats(broadcaster_id: int) -> dict:
        """Get transcription statistics for a broadcaster."""
        # Get all videos for the broadcaster
        all_videos_count = db.session.query(func.count(Video.id)).join(Video.channel).filter(
            Channels.broadcaster_id == broadcaster_id
        ).scalar() or 0

        # Get all videos with at least one high quality transcription (Unknown source)
        high_quality_videos = db.session.query(Video.id).distinct().join(Video.transcriptions).join(Video.channel).filter(
            Channels.broadcaster_id == broadcaster_id,
            Video.active == True,
            Transcription.source == TranscriptionSource.Unknown
        ).all()
        high_quality_video_ids = {video_id for (
            video_id,) in high_quality_videos}
        high_quality_count = len(high_quality_video_ids)

        # Get videos with low quality transcriptions (YouTube source) but no high quality ones
        query = db.session.query(Video.id).distinct().join(Video.transcriptions).join(Video.channel).filter(
            Channels.broadcaster_id == broadcaster_id,
            Transcription.source == TranscriptionSource.YouTube,
            Video.active == True
        )

        if high_quality_video_ids:
            query = query.filter(~Video.id.in_(high_quality_video_ids))

        low_quality_videos = query.all()
        low_quality_count = len(low_quality_videos)

        # Count videos with no transcriptions
        with_transcriptions_videos = db.session.query(Video.id).distinct().join(Video.transcriptions).join(Video.channel).filter(
            Channels.broadcaster_id == broadcaster_id,
            Video.active == True,
        ).all()
        with_transcriptions_video_ids = {video_id for (
            video_id,) in with_transcriptions_videos}
        no_transcriptions_count = all_videos_count - \
            len(with_transcriptions_video_ids)

        return {
            'high_quality': high_quality_count,
            'low_quality': low_quality_count,
            'no_transcription': no_transcriptions_count
        }

    @staticmethod
    def delete(broadcaster_id: int) -> bool:
        """Delete a broadcaster and all associated data."""
        try:
            broadcaster = BroadcasterService.get_by_id(broadcaster_id)

            # Delete associated channels using the proper channel service
            from .channel import ChannelService
            channels_to_delete = list(broadcaster.channels)  # Create a copy to avoid iteration issues
            for channel in channels_to_delete:
                ChannelService.delete_channel(channel.id)

            # Delete broadcaster settings
            db.session.query(BroadcasterSettings).filter_by(
                broadcaster_id=broadcaster_id
            ).delete()

            # Delete content queue settings
            db.session.query(ContentQueueSettings).filter_by(
                broadcaster_id=broadcaster_id
            ).delete()

            # Delete user weights
            from app.models.user import UserWeight
            db.session.query(UserWeight).filter_by(
                broadcaster_id=broadcaster_id
            ).delete()

            # Delete the broadcaster
            db.session.query(Broadcaster).filter_by(id=broadcaster_id).delete()
            db.session.commit()

            logger.info(f"Deleted broadcaster {broadcaster_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete broadcaster {broadcaster_id}: {e}")
            db.session.rollback()
            return False

    @staticmethod
    def get_last_active(broadcaster_id: int) -> datetime | None:
        """Get the last active timestamp for a broadcaster."""
        return db.session.query(func.max(Channels.last_active)).filter_by(
            broadcaster_id=broadcaster_id
        ).scalar()

    @staticmethod
    def create(name: str, hidden: bool = False) -> Broadcaster:
        """Create a new broadcaster."""
        broadcaster = Broadcaster(name=name, hidden=hidden)
        db.session.add(broadcaster)
        db.session.commit()
        logger.info(f"Created broadcaster: {name}")
        return broadcaster

    @staticmethod
    def update(broadcaster_id: int, **kwargs) -> Broadcaster:
        """Update broadcaster fields."""
        broadcaster = BroadcasterService.get_by_id(broadcaster_id)
        for key, value in kwargs.items():
            if hasattr(broadcaster, key):
                setattr(broadcaster, key, value)
        db.session.commit()
        return broadcaster

    @staticmethod
    def hide(broadcaster_id: int) -> Broadcaster:
        """Hide a broadcaster."""
        return BroadcasterService.update(broadcaster_id, hidden=True)

    @staticmethod
    def unhide(broadcaster_id: int) -> Broadcaster:
        """Unhide a broadcaster."""
        return BroadcasterService.update(broadcaster_id, hidden=False)


# For template accessibility, create a simple function interface
def get_broadcaster_service() -> BroadcasterService:
    """Get broadcaster service instance for use in templates."""
    return BroadcasterService()
