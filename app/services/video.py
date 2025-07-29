"""
Video service for handling video-related business logic.
"""
import asyncio
from collections.abc import Sequence

from sqlalchemy import select, func
from app.models import db
from app.models import Video, VideoCreate, Transcription, TranscriptionSource, VideoType, PlatformType
from app.logger import logger
from app.models.config import config
from app.tasks import get_yt_audio, get_twitch_audio
from app.utils import save_generic_thumbnail
from app.youtube_api import fetch_transcription
from youtube_transcript_api.formatters import WebVTTFormatter


class VideoService:
    """Service class for video-related operations."""

    @staticmethod
    def get_by_id(video_id: int) -> Video:
        """Get video by ID."""
        return db.session.execute(
            select(Video).filter_by(id=video_id)
        ).scalars().one()

    @staticmethod
    def get_by_platform_ref(platform_ref: str) -> Video | None:
        """Get video by platform reference."""
        return db.session.execute(
            select(Video).filter_by(platform_ref=platform_ref)
        ).scalars().one_or_none()

    @staticmethod
    def get_count() -> int:
        return db.session.query(func.count(Video.id)).scalar()

    @staticmethod
    def get_videos_by_channel(channel_id: int) -> Sequence[Video]:
        """Get all videos for a channel, ordered by upload date."""
        return db.session.execute(
            select(Video)
            .filter_by(channel_id=channel_id)
            .order_by(Video.uploaded.desc())
        ).scalars().all()

    @staticmethod
    def get_date_str(video: Video) -> str:
        """Get formatted date string for a video."""
        return video.uploaded.strftime("%d.%m.%Y")

    @staticmethod
    def get_duration_str(video: Video) -> str:
        """Get formatted duration string for a video."""
        return VideoService._seconds_to_string(video.duration)

    @staticmethod
    def _seconds_to_string(seconds: float) -> str:
        """Convert seconds to duration string (HH:MM:SS or MM:SS)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds_remainder = int(seconds % 60)

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds_remainder:02d}"
        else:
            return f"{minutes:02d}:{seconds_remainder:02d}"

    @staticmethod
    def get_url(video: Video) -> str:
        """Get the URL for a video based on its platform."""
        # TODO: Extract platform URLs from platform config
        if str(video.channel.platform_name).lower() == "youtube":
            return f"https://www.youtube.com/watch?v={video.platform_ref}"
        elif str(video.channel.platform_name).lower() == "twitch":
            return f"https://www.twitch.tv/videos/{video.platform_ref}"
        raise ValueError(f"Could not generate url for video: {video.id}")

    @staticmethod
    def get_url_with_timestamp(video: Video, seconds_offset: float) -> str:
        """Generate a URL to the video at a specific timestamp.

        Args:
            video: The video instance
            seconds_offset: Number of seconds from the start of the video

        Returns:
            URL string with appropriate timestamp format for the platform
        """
        base_url = VideoService.get_url(video)

        # Ensure seconds_offset is positive and within video duration
        seconds_offset = max(0, min(seconds_offset, video.duration))

        # Format timestamp based on platform
        if str(video.channel.platform_name).lower() == "youtube":
            # YouTube uses t=123s format (seconds)
            return f"{base_url}&t={int(seconds_offset)}s"
        elif str(video.channel.platform_name).lower() == "twitch":
            # Twitch uses t=01h23m45s format
            hours = int(seconds_offset // 3600)
            minutes = int((seconds_offset % 3600) // 60)
            seconds = int(seconds_offset % 60)

            if hours > 0:
                timestamp = f"{hours:02d}h{minutes:02d}m{seconds:02d}s"
            else:
                timestamp = f"{minutes:02d}m{seconds:02d}s"

            return f"{base_url}?t={timestamp}"

        # Default fallback
        return base_url

    @staticmethod
    def delete_video(video: Video) -> bool:
        """Delete a video and all associated data."""
        try:

            # Delete associated transcriptions (cascade will handle segments)
            from .transcription import TranscriptionService
            for transcription in video.transcriptions:
                TranscriptionService.delete_transcription(transcription.id)

            # Delete the video
            db.session.query(Video).filter_by(id=video.id).delete()
            db.session.commit()

            logger.info(f"Deleted video {video.id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete video {video.id}: {e}")
            db.session.rollback()
            return False

    @staticmethod
    def archive_video(video: Video):
        """Archive a video by transferring transcriptions to linked VOD videos."""
        for linked_video in video.video_refs:
            if linked_video.video_type == VideoType.VOD:
                for transcription in video.transcriptions:
                    transcription.video_id = linked_video.id
                    logger.info(
                        f"Transcription id: {transcription.id} on video id {video.id} is transferred to {linked_video.id}"
                    )
                db.session.commit()

    @staticmethod
    def fetch_details(video: Video, force: bool = True):
        """Fetch and update video details from platform APIs."""
        from .platform import PlatformServiceRegistry
        platform_service = PlatformServiceRegistry.get_service(
            PlatformType(video.channel.platform_name))
        if platform_service is None:
            raise ValueError(
                f"Platform service not found for platform {video.channel.platform_name}")
        video_details = asyncio.run(
            platform_service.fetch_video_details(video.platform_ref))

        if video.duration != video_details.duration:
            # Handle duration change logic
            logger.warning(
                f"Duration changed for video {video.platform_ref}: {video.duration} -> {video_details.duration}"
            )
            for transcription in video.transcriptions:
                from .transcription import TranscriptionService
                TranscriptionService.delete_transcription(transcription.id)
            try:
                if video.audio is not None:
                    video.audio.file.object.delete()
            except Exception as e:
                logger.error(
                    f"Failed to delete audio for video {video.platform_ref}, exception: {e}")
            video.audio = None
            video.duration = video_details.duration

            video.title = video_details.title
            video.uploaded = video_details.uploaded
            tn = save_generic_thumbnail(video_details.thumbnail_url)
            video.thumbnail = open(tn, "rb")  # type: ignore[assignment]
            logger.info(f"Fetched details for video {video.platform_ref}")

        db.session.commit()

    @staticmethod
    def download_transcription(video: Video, force: bool = False):
        """Download transcription from platform (YouTube only)."""
        if force:
            for transcription in video.transcriptions:
                if transcription.source == TranscriptionSource.YouTube:
                    logger.info(
                        f"Transcriptions found {video.platform_ref}, forcing delete")
                    db.session.delete(transcription)
            db.session.commit()

        if len(video.transcriptions) == 0:
            logger.info(
                f"Transcriptions not found on {video.platform_ref}, adding new..")

            formatter = WebVTTFormatter()
            path = config.cache_location + video.platform_ref + ".vtt"
            fetched_transcription = fetch_transcription(video.platform_ref)
            t_formatted = formatter.format_transcript(fetched_transcription)
            with open(path, "w", encoding="utf-8") as vtt_file:
                vtt_file.write(t_formatted)
            from .transcription import TranscriptionService
            TranscriptionService.create(
                video_id=video.id,
                language=transcription.language,
                file_extension="vtt",
                file_content=open(path, "rb"),
                source=TranscriptionSource.YouTube
            )

            logger.info(
                f"Would download transcription for video {video.platform_ref}")
            db.session.commit()

    @staticmethod
    def process_transcriptions(video: Video, force: bool = False):
        """Process transcriptions for a video."""
        transcription_to_process: Transcription | None = None

        from .transcription import TranscriptionService

        for transcription in video.transcriptions:
            if force:
                TranscriptionService.reset_transcription(transcription)
            if len(video.transcriptions) == 1:
                transcription_to_process = transcription
            if (
                len(video.transcriptions) > 1
                and transcription.source is not TranscriptionSource.YouTube
            ):
                transcription_to_process = transcription
            if len(video.transcriptions) > 1 and transcription.source is TranscriptionSource.YouTube:
                TranscriptionService.reset_transcription(transcription)

        logger.info(
            f"Processing transcriptions for {video.id}, found {transcription_to_process}"
        )
        if transcription_to_process is not None:
            TranscriptionService.reset_transcription(transcription_to_process)
            TranscriptionService.process_transcription(
                transcription_to_process, force)

    @staticmethod
    def save_audio(video: Video, force: bool = False):
        """Save audio for a video."""
        if str(video.channel.platform_name).lower() == "twitch":
            audio = get_twitch_audio(VideoService.get_url(video))
            video.audio = open(audio, "rb")  # type: ignore[assignment]
            db.session.commit()
        elif str(video.channel.platform_name).lower() == "youtube":
            audio = get_yt_audio(VideoService.get_url(video))
            video.audio = open(audio, "rb")  # type: ignore[assignment]
            db.session.commit()

    @staticmethod
    def create(video: VideoCreate) -> Video:
        """Create a new video."""
        thumbnail = save_generic_thumbnail(video.thumbnail_url)
        added_video = Video(
            title=video.title,
            video_type=video.video_type,
            duration=video.duration,
            channel_id=video.channel_id,
            platform_ref=video.platform_ref,
            uploaded=video.uploaded,
            active=video.active,
            source_video_id=video.source_video_id,
            thumbnail=open(thumbnail, "rb")
        )
        db.session.add(added_video)
        db.session.commit()
        logger.info(f"Created video: {video.title}")
        return added_video

    @staticmethod
    def update(video_id: int, **kwargs) -> Video:
        """Update video fields."""
        video = VideoService.get_by_id(video_id)
        for key, value in kwargs.items():
            if hasattr(video, key):
                setattr(video, key, value)
        db.session.commit()
        return video

    @staticmethod
    def activate(video_id: int) -> Video:
        """Activate a video."""
        return VideoService.update(video_id, active=True)

    @staticmethod
    def deactivate(video_id: int) -> Video:
        """Deactivate a video."""
        return VideoService.update(video_id, active=False)


# For template accessibility, create simple function interfaces
def get_video_service() -> VideoService:
    """Get video service instance for use in templates."""
    return VideoService()


def video_get_url(video: Video) -> str:
    """Get video URL for use in templates."""
    return VideoService.get_url(video)


def video_get_url_with_timestamp(video: Video, seconds_offset: float) -> str:
    """Get video URL with timestamp for use in templates."""
    return VideoService.get_url_with_timestamp(video, seconds_offset)


def video_get_date_str(video: Video) -> str:
    """Get formatted date string for use in templates."""
    return VideoService.get_date_str(video)


def video_get_duration_str(video: Video) -> str:
    """Get formatted duration string for use in templates."""
    return VideoService.get_duration_str(video)
