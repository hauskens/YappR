"""
Channel service for handling channel-related business logic.
"""
import asyncio
from collections.abc import Sequence
from typing import Optional

from sqlalchemy import select, func, update
from sqlalchemy.orm import aliased
from datetime import datetime
from app.models import db
from app.models import (
    Video, Platforms, Broadcaster, Channels, Transcription,
    ChannelSettings, ContentQueue, ContentQueueSubmission, ChatLog, ChannelCreate,
    TranscriptionSource, Users, TimestampMapping
)
from app.models.channel import ChannelEvent
from app.models.enums import AccountSource
from app.models.user import ModerationAction, UserChannelRole
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
    def get_by_platform_channel_id(platform_channel_id: str) -> Channels | None:
        """Get channel by platform channel ID."""
        return db.session.execute(
            select(Channels).filter_by(platform_channel_id=platform_channel_id)
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
        # Create alias for source video to avoid naming conflicts
        SourceVideo = aliased(Video)
        
        # Videos with direct transcriptions
        direct_transcriptions = (
            db.session.query(Video.id)
            .filter(
                Video.transcriptions.any(
                    Transcription.source == TranscriptionSource.Unknown
                ),
                Video.channel_id == channel_id,
            )
        )
        
        # Videos linked to sources with transcriptions
        linked_transcriptions = (
            db.session.query(Video.id)
            .join(TimestampMapping, Video.id == TimestampMapping.target_video_id)
            .join(SourceVideo, TimestampMapping.source_video_id == SourceVideo.id)
            .filter(
                SourceVideo.transcriptions.any(
                    Transcription.source == TranscriptionSource.Unknown
                ),
                Video.channel_id == channel_id,
            )
        )
        
        # Union both queries and count distinct video IDs
        combined_query = direct_transcriptions.union(linked_transcriptions)
        return db.session.query(func.count()).select_from(combined_query.subquery()).scalar() or 0


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

            # Delete moderation actions
            db.session.query(ModerationAction).filter_by(
                channel_id=channel_id).delete()

            # Delete user channel roles
            db.session.query(UserChannelRole).filter_by(
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
    def look_for_linked_videos(channel: Channels, margin_sec: int = 2, min_duration: int = 300, date_margin_hours: int = 48):
        """
        Look for videos that should be linked based on duration matching and/or title date matching.
        
        Args:
            channel: Target channel to link videos for
            margin_sec: Duration matching margin in seconds
            min_duration: Minimum video duration for linking
            date_margin_hours: Maximum time difference for date-based matching
        """
        if not channel.source_channel:
            logger.warning(
                f"Channel {channel.name} has no source channel for linking")
            return

        # Title date parsing is always enabled
        title_parsing_enabled = True
        
        logger.info(f"Looking for potential links on channel {channel.name} "
                   f"(duration matching: always, title parsing: {title_parsing_enabled})")
        
        # Process title dates if enabled
        if title_parsing_enabled:
            ChannelService._process_title_dates(channel)
        
        matches_found = 0
        
        for source_video in channel.source_channel.videos:
            for target_video in channel.videos:
                if target_video.is_linked_to_source():
                    continue  # Already linked
                
                # Duration-based matching (existing logic)
                duration_match = (
                    target_video.duration > min_duration
                    and (source_video.duration - margin_sec)
                    <= target_video.duration
                    <= (source_video.duration + margin_sec)
                )
                
                # Date-based matching (new logic)
                date_match = False
                if title_parsing_enabled and target_video.estimated_upload_time and source_video.uploaded:
                    time_diff = abs((target_video.estimated_upload_time - source_video.uploaded).total_seconds() / 3600)
                    date_match = time_diff <= date_margin_hours
                    
                    if date_match:
                        logger.debug(f"Date match found: {target_video.title[:50]}... "
                                   f"(estimated: {target_video.estimated_upload_time}, "
                                   f"source: {source_video.uploaded}, diff: {time_diff:.1f}h)")
                
                # Link if either duration or date matches (or both)
                if duration_match or date_match:
                    match_reason = []
                    if duration_match:
                        match_reason.append("duration")
                    if date_match:
                        match_reason.append("date")
                    
                    logger.info(
                        f"Found match ({', '.join(match_reason)})! "
                        f"Source: {source_video.id} -> Target: {target_video.id}"
                    )
                    from .video import VideoService
                    VideoService.add_timestamp_mapping(target_video, source_video)
                    db.session.flush()
                    matches_found += 1
        
        db.session.commit()
        logger.info(f"Linked {matches_found} videos for channel {channel.name}")
    
    @staticmethod
    def _process_title_dates(channel: Channels):
        """Process title dates for unlinked videos in the channel."""
        from app.utils import extract_date_from_video_title
        
        updated_count = 0
        for video in channel.videos:
            if not video.is_linked_to_source() and video.estimated_upload_time is None:
                extracted_date = extract_date_from_video_title(video.title)
                if extracted_date:
                    video.estimated_upload_time = extracted_date
                    db.session.flush()
                    updated_count += 1
        
        if updated_count > 0:
            logger.info(f"Updated estimated upload times for {updated_count} videos in {channel.name}")
            db.session.commit()

    @staticmethod
    def bulk_auto_link_videos(channel: Channels, margin_sec: int = 10, min_duration: int = 300, date_margin_hours: int = 48) -> int:
        """
        Bulk auto-link videos where BOTH Duration AND Date matches are found.
        This is more restrictive than look_for_linked_videos() which requires only one match.
        
        Args:
            channel: Target channel to link videos for
            margin_sec: Duration matching margin in seconds
            min_duration: Minimum video duration for linking
            date_margin_hours: Maximum time difference for date-based matching
            
        Returns:
            Number of videos that were successfully auto-linked
        """
        if not channel.source_channel:
            logger.warning(f"Channel {channel.name} has no source channel for linking")
            return 0

        logger.info(f"Running bulk auto-link for channel {channel.name} (requires BOTH duration AND date match)")
        
        # Process title dates if needed
        ChannelService._process_title_dates(channel)
        
        linked_count = 0
        
        for source_video in channel.source_channel.videos:
            for target_video in channel.videos:
                if target_video.is_linked_to_source():
                    continue  # Already linked
                
                # Duration-based matching (same as existing logic)
                duration_match = (
                    target_video.duration > min_duration
                    and (source_video.duration - margin_sec)
                    <= target_video.duration
                    <= (source_video.duration + margin_sec)
                )
                
                # Date-based matching (same as existing logic)
                date_match = False
                if target_video.estimated_upload_time and source_video.uploaded:
                    time_diff = abs((target_video.estimated_upload_time - source_video.uploaded).total_seconds() / 3600)
                    date_match = time_diff <= date_margin_hours
                
                # Auto-link only if BOTH conditions are met
                if duration_match and date_match:
                    logger.info(
                        f"Auto-linking (duration + date match)! "
                        f"Source: {source_video.id} -> Target: {target_video.id} "
                        f"(duration diff: {abs(target_video.duration - source_video.duration):.1f}s, "
                        f"time diff: {time_diff:.1f}h)"
                    )
                    from .video import VideoService
                    VideoService.add_timestamp_mapping(target_video, source_video)
                    db.session.flush()
                    linked_count += 1
        
        db.session.commit()
        logger.info(f"Auto-linked {linked_count} videos for channel {channel.name}")
        return linked_count

    @staticmethod
    def fetch_all_videos(channel: Channels):
        """Fetch all videos from platform."""
        from .platform import PlatformServiceRegistry
        from .video import VideoService
        
        platform_service = PlatformServiceRegistry.get_service_for_channel(channel)
        if platform_service is None:
            logger.error(f"Platform {channel.platform_name} not found")
            return None

        # Use fetch_latest_videos with a very large limit to get all videos
        videos = asyncio.run(platform_service.fetch_latest_videos(channel, limit=999999))
        if videos is None:
            logger.error(f"Failed to fetch all videos for channel {channel.name}")
            return None

        logger.info(f"Fetched {len(videos)} videos for channel {channel.name}")
        
        successful_count = 0
        failed_count = 0
        for v in channel.videos:
            v.active = False
        db.session.flush()
        
        for video in videos:
            try:
                existing_video = VideoService.get_by_platform_ref(video.platform_ref)
                if existing_video is None:
                    VideoService.create(video)
                    logger.info(f"Created video: {video.title}")
                else:
                    # Update existing video details
                    existing_video.title = video.title
                    existing_video.video_type = video.video_type
                    existing_video.duration = video.duration
                    existing_video.uploaded = video.uploaded
                    existing_video.active = video.active
                    logger.debug(f"Updated video: {video.title}")
                successful_count += 1
            except Exception as e:
                failed_count += 1
                logger.error(f"Failed to process video '{video.title}': {e}")
                # Continue processing other videos
                continue

        db.session.commit()
        logger.info(f"Successfully processed {successful_count} videos for channel {channel.name}. Failed: {failed_count}")
        

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

        successful_count = 0
        failed_count = 0
        
        for video in videos:
            try:
                existing_video = VideoService.get_by_platform_ref(
                    video.platform_ref)
                if existing_video is None:
                    VideoService.create(video)
                    logger.info(f"Created video: {video.title}")
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
                    logger.debug(f"Updated video: {video.title}")
                successful_count += 1
            except Exception as e:
                failed_count += 1
                logger.error(f"Failed to process video '{video.title}': {e}")
                # Continue processing other videos
                continue

        db.session.commit()
        logger.info(f"Successfully processed {successful_count} videos for channel {channel.name}. Failed: {failed_count}")

    @staticmethod
    def create(channel_create: ChannelCreate) -> Channels:
        """Create a new channel."""
        channel = Channels(
            name=channel_create.name,
            broadcaster_id=channel_create.broadcaster_id,
            platform_name=channel_create.platform_name,
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

    @staticmethod
    def match_channel_event_users() -> dict:
        """
        Match ChannelEvents without user_id to Users with Twitch accounts.
        
        Returns:
            Dictionary with matching results and statistics
        """
        results = {
            'status': 'success',
            'total_unmatched': 0,
            'total_matched': 0,
            'errors': [],
            'started_at': datetime.now().isoformat(),
            'completed_at': None
        }
        
        try:
            # Load all Twitch users into memory for fast lookups
            logger.info("Loading Twitch users into memory")
            twitch_users = db.session.query(Users.name, Users.id).filter(
                Users.account_type == AccountSource.Twitch
            ).all()
            
            username_to_user_id = {user.name.lower(): user.id for user in twitch_users}
            logger.info(f"Loaded {len(username_to_user_id):,} Twitch users for matching")
            
            if not username_to_user_id:
                results['status'] = 'warning'
                results['errors'].append("No Twitch users found in database")
                results['completed_at'] = datetime.now().isoformat()
                return results
            
            # Get all unmatched channel events
            unmatched_events = db.session.query(ChannelEvent).filter(
                ChannelEvent.user_id.is_(None),
                ChannelEvent.username.is_not(None)
            ).all()
            
            results['total_unmatched'] = len(unmatched_events)
            logger.info(f"Found {len(unmatched_events):,} unmatched ChannelEvents")
            
            if not unmatched_events:
                results['completed_at'] = datetime.now().isoformat()
                return results
            
            # Match and update events
            matched_count = 0
            for event in unmatched_events:
                normalized_username = event.username.lower()
                if normalized_username in username_to_user_id:
                    event.user_id = username_to_user_id[normalized_username]
                    matched_count += 1
            
            # Commit all changes
            db.session.commit()
            
            results['total_matched'] = matched_count
            results['completed_at'] = datetime.now().isoformat()
            
            logger.info(f"ChannelEvent matching completed - matched: {matched_count:,} of {len(unmatched_events):,} events")
            
        except Exception as e:
            logger.error(f"Error during ChannelEvent user matching: {e}")
            db.session.rollback()
            results['status'] = 'error'
            results['errors'].append(str(e))
            results['completed_at'] = datetime.now().isoformat()
            
        return results


# For template accessibility, create simple function interfaces
def get_channel_service() -> ChannelService:
    """Get channel service instance for use in templates."""
    return ChannelService()
