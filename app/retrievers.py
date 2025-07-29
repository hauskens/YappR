from collections.abc import Sequence
from sqlalchemy import select, func, or_
from .models import db
from .models.auth import Permissions, OAuth
from .models.platform import Platforms
from .models.video import Video
from .models.transcription import Transcription, Segments
from .models.content_queue import ContentQueue
from .models.enums import TranscriptionSource
from app.logger import logger

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
