from collections.abc import Sequence
from sqlalchemy import select, func, or_
from .models.db import (
    Broadcaster,
    Permissions,
    Platforms,
    Segments,
    TranscriptionSource,
    Channels,
    Video,
    Transcription,
    Users,
    OAuth,
    ContentQueue,
    ChannelModerator,
    db,
)
from .tasks import (
    get_yt_audio,
)
from datetime import datetime
from app.logger import logger
from app.cache import cache, make_cache_key

def get_broadcasters(show_hidden: bool = False) -> Sequence[Broadcaster]:
    if show_hidden:
        return (
            db.session.execute(select(Broadcaster).order_by(Broadcaster.id)).scalars().all()
        )
    else:
        return (
            db.session.execute(select(Broadcaster).filter_by(hidden=False).order_by(Broadcaster.id)).scalars().all()
        )


def get_broadcaster(broadcaster_id: int) -> Broadcaster:
    return (
        db.session.execute(select(Broadcaster).filter_by(id=broadcaster_id))
        .scalars()
        .one()
    )


def get_channel(channel_id: int) -> Channels:
    return db.session.execute(select(Channels).filter_by(id=channel_id)).scalars().one()


def get_platforms() -> Sequence[Platforms] | None:
    return db.session.execute(select(Platforms)).scalars().all()


def get_broadcaster_channels(broadcaster_id: int) -> Sequence[Channels] | None:
    return (
        db.session.execute(select(Channels).filter_by(broadcaster_id=broadcaster_id))
        .scalars()
        .all()
    )


def get_broadcaster_transcription_stats(broadcaster_id: int) -> dict:
    # Get all videos for the broadcaster
    all_videos_count = db.session.query(func.count(Video.id)).join(Video.channel).filter(
        Channels.broadcaster_id == broadcaster_id
    ).scalar() or 0
    
    # Get all videos with at least one high quality transcription (Unknown source)
    # These are counted first since high quality takes precedence
    high_quality_videos = db.session.query(Video.id).distinct().join(Video.transcriptions).join(Video.channel).filter(
        Channels.broadcaster_id == broadcaster_id,
        Video.active == True,
        Transcription.source == TranscriptionSource.Unknown
    ).all()
    high_quality_video_ids = {video_id for (video_id,) in high_quality_videos}
    high_quality_count = len(high_quality_video_ids)
    
    # Get videos with low quality transcriptions (YouTube source) but no high quality ones
    query = db.session.query(Video.id).distinct().join(Video.transcriptions).join(Video.channel).filter(
        Channels.broadcaster_id == broadcaster_id,
        Transcription.source == TranscriptionSource.YouTube,
        Video.active == True
    )
    
    # Only apply the filter if there are high quality videos to exclude
    if high_quality_video_ids:
        query = query.filter(~Video.id.in_(high_quality_video_ids))
        
    low_quality_videos = query.all()
    low_quality_count = len(low_quality_videos)
    
    # Count videos with no transcriptions
    with_transcriptions_videos = db.session.query(Video.id).distinct().join(Video.transcriptions).join(Video.channel).filter(
        Channels.broadcaster_id == broadcaster_id,
        Video.active == True,
    ).all()
    with_transcriptions_video_ids = {video_id for (video_id,) in with_transcriptions_videos}
    no_transcriptions_count = all_videos_count - len(with_transcriptions_video_ids)
    
    return {
        'high_quality': high_quality_count,
        'low_quality': low_quality_count,
        'no_transcription': no_transcriptions_count
    }


def get_video(video_id: int) -> Video:
    return db.session.execute(select(Video).filter_by(id=video_id)).scalars().one()


def get_video_by_channel(channel_id: int) -> Sequence[Video] | None:
    return (
        db.session.execute(
            select(Video)
            .filter_by(channel_id=channel_id)
            .order_by(Video.uploaded.desc())
        )
        .scalars()
        .all()
    )


def get_video_by_ref(video_platform_ref: str) -> Video | None:
    return (
        db.session.execute(select(Video).filter_by(platform_ref=video_platform_ref))
        .scalars()
        .one_or_none()
    )


def get_transcriptions_by_video(video_id: int) -> Sequence[Transcription] | None:
    return (
        db.session.execute(select(Transcription).filter_by(video_id=video_id))
        .scalars()
        .all()
    )


def get_transcription(transcription_id: int) -> Transcription:
    return (
        db.session.execute(select(Transcription).filter_by(id=transcription_id))
        .scalars()
        .one()
    )


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
    return db.session.query(Segments).filter_by(id=segment_id).one()


def delete_broadcaster(broadcaster_id: int):
    return db.session.query(Broadcaster).filter_by(id=broadcaster_id).delete()


def get_users() -> list[Users]:
    return db.session.query(Users).all()

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


def get_stats_videos_with_audio(channel_id: int) -> int:
    return (
        db.session.query(func.count(func.distinct(Video.id)))
        .filter(Video.audio.is_not(None), Video.channel_id == channel_id)
        .scalar() or 0
    )


def get_stats_videos_with_good_transcription(channel_id: int) -> int:
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

def get_moderated_channels(user_id: int) -> list[ChannelModerator]:
    return db.session.query(ChannelModerator).filter_by(user_id=user_id).all()
    

def get_stats_segments() -> int:
    return db.session.query(Segments).count()


def get_user_permissions(user: Users) -> list[Permissions]:
    return db.session.query(Permissions).filter_by(user_id=user.id).all()


def get_user_by_ext(user_external_id: str) -> Users:
    return db.session.query(Users).filter_by(external_account_id=user_external_id).one()


def get_user_by_id(user_id: int) -> Users:
    return db.session.query(Users).filter_by(id=user_id).one()


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

def get_broadcaster_by_external_id(external_id: str) -> Broadcaster | None:
    return db.session.execute(
        select(Broadcaster)
        .join(Broadcaster.channels)
        .where(Channels.platform_channel_id == external_id)
        .limit(1)
    ).scalars().one_or_none()

def get_all_twitch_channels() -> Sequence[Channels]:
    """Get all Twitch channels"""
    return (
        db.session.execute(
            select(Channels)
            .join(Platforms)
            .filter(Platforms.name.ilike("twitch"))
            .order_by(Channels.name)
        )
        .scalars()
        .all()
    )


def fetch_audio(video_id: int):
    video = get_video(video_id)
    video_url = video.get_url()
    if video.audio is None:
        if video_url is not None:
            logger.info(f"fetching audio for {video_url}")
            audio = get_yt_audio(video_url)
            logger.info(f"adding audio on {video_id}..")
            video.audio = open(audio, "rb") # type: ignore
            db.session.commit()
    else:
        logger.info(f"skipped audio for {video_url}, already exists.")
