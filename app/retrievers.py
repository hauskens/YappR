from collections.abc import Sequence
from sqlalchemy import select, func, or_
from .models import db
from .models.broadcaster import Broadcaster
from .models.auth import Permissions, OAuth
from .models.channel import Channels, ChannelModerator
from .models.platform import Platforms
from .models.video import Video
from .models.transcription import Transcription, Segments
from .models.user import Users
from .models.content_queue import ContentQueue
from .models.enums import TranscriptionSource
from .tasks import (
    get_yt_audio,
)
from datetime import datetime
from app.logger import logger
from app.cache import cache, make_cache_key
from .services.user import UserService



def get_platforms() -> Sequence[Platforms] | None:
    return db.session.execute(select(Platforms)).scalars().all()


def get_video(video_id: int) -> Video:
    return VideoService.get_by_id(video_id)


def get_video_by_ref(video_platform_ref: str) -> Video | None:
    return VideoService.get_by_platform_ref(video_platform_ref)


def get_transcriptions_by_video(video_id: int) -> Sequence[Transcription] | None:
    return TranscriptionService.get_by_video_id(video_id)


def get_transcription(transcription_id: int) -> Transcription:
    return TranscriptionService.get_by_id(transcription_id)


def get_transcriptions_on_channels(
    channels: Sequence[Channels],
) -> Sequence[Transcription]:
    transcriptions: list[Transcription] = []
    for channel in channels:
        for video in channel.videos:
            if video.active:
                transcriptions += video.transcriptions
    return transcriptions


def get_transcriptions_on_channels_daterange(
    channels: Sequence[Channels], start_date: datetime, end_date: datetime
) -> Sequence[Transcription]:
    transcriptions: list[Transcription] = []
    for channel in channels:
        for video in channel.videos:
            if video.active:
                logger.debug(
                    f"Checking DATE: {start_date} < {video.uploaded} < {end_date}"
                )
                if start_date <= video.uploaded <= end_date:
                    transcriptions += video.transcriptions
                    logger.debug("Found match!")
    return transcriptions


def get_segment_by_id(segment_id: int) -> Segments:
    return SegmentService.get_by_id(segment_id)



def get_users() -> list[Users]:
    return UserService.get_all()


def get_bots() -> list[OAuth]:
    return db.session.query(OAuth).filter_by(provider="twitch_bot").all()


def get_stats_videos() -> int:
    return db.session.query(Video).count()


def get_total_video_duration() -> int:
    total_duration = db.session.query(func.sum(Video.duration)).scalar()
    return total_duration or 0


def get_total_good_transcribed_video_duration() -> int:
    total_duration = db.session.query(func.sum(Video.duration)).filter(
        Video.transcriptions.any(
            Transcription.source == TranscriptionSource.Unknown
        )
    ).scalar()
    return total_duration or 0


def get_total_low_quality_transcribed_video_duration() -> int:
    total_duration = db.session.query(func.sum(Video.duration)).filter(
        Video.transcriptions.any(
            Transcription.source == TranscriptionSource.YouTube
        ),
        ~Video.transcriptions.any(
            Transcription.source == TranscriptionSource.Unknown
        )
    ).scalar()
    return total_duration or 0



def get_stats_videos_with_low_transcription() -> int:
    return (
        db.session.query(func.count(func.distinct(Video.id)))
        .filter(
            Video.transcriptions.any(
                Transcription.source == TranscriptionSource.YouTube
            ),
            ~Video.transcriptions.any(
                Transcription.source == TranscriptionSource.Unknown
            )
        )
        .scalar() or 0
    )


def get_stats_transcriptions() -> int:
    return db.session.query(func.count(func.distinct(Transcription.video_id))).scalar() or 0


def get_stats_high_quality_transcriptions() -> int:
    return (
        db.session.query(func.count(func.distinct(Transcription.video_id)))
        .filter(Transcription.source == TranscriptionSource.Unknown)
        .scalar() or 0
    )


def get_stats_segments() -> int:
    return db.session.query(Segments).count()


def get_user_permissions(user: Users) -> list[Permissions]:
    return UserService.get_permissions(user)


def get_user_by_ext(user_external_id: str) -> Users:
    return UserService.get_by_external_id(user_external_id)


def get_user_by_id(user_id: int) -> Users:
    return UserService.get_by_id(user_id)


def get_content_queue(broadcaster_id: int | None = None, include_skipped: bool = False, include_watched: bool = False) -> Sequence[ContentQueue]:
    """Get content queue items, optionally filtered by broadcaster_id"""
    query = select(ContentQueue)
    if broadcaster_id is not None:
        query = query.filter(ContentQueue.broadcaster_id == broadcaster_id)
        if not include_skipped:
            query = query.filter(ContentQueue.skipped == False)
        if not include_watched:
            query = query.filter(ContentQueue.watched == include_watched)
    return db.session.execute(query.order_by(ContentQueue.id.desc())).scalars().all()


def fetch_audio(video_id: int):
    video = get_video(video_id)
    video_url = VideoService.get_url(video)
    if video.audio is None:
        if video_url is not None:
            logger.info(f"fetching audio for {video_url}")
            audio = get_yt_audio(video_url)
            logger.info(f"adding audio on {video_id}..")
            video.audio = open(audio, "rb")  # type: ignore
            db.session.commit()
    else:
        logger.info(f"skipped audio for {video_url}, already exists.")
