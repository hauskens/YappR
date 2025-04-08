import logging
from collections.abc import Sequence
from sqlalchemy import DateTime, select
from .models.db import (
    Broadcaster,
    Platforms,
    Segments,
    WordMaps,
    Channels,
    Video,
    Transcription,
    TranscriptionSource,
    db,
)
from .tasks import (
    get_yt_video_subtitles,
    get_yt_audio,
)
from datetime import datetime

logger = logging.getLogger(__name__)


def get_broadcasters() -> Sequence[Broadcaster]:
    return (
        db.session.execute(select(Broadcaster).order_by(Broadcaster.id)).scalars().all()
    )


def get_broadcaster(broadcaster_id: int) -> Broadcaster | None:
    return (
        db.session.execute(select(Broadcaster).filter_by(id=broadcaster_id))
        .scalars()
        .one_or_none()
    )


def get_platforms() -> Sequence[Platforms] | None:
    return db.session.execute(select(Platforms)).scalars().all()


def get_broadcaster_channels(broadcaster_id: int) -> Sequence[Channels] | None:
    return (
        db.session.execute(select(Channels).filter_by(broadcaster_id=broadcaster_id))
        .scalars()
        .all()
    )


def get_channel(channel_id: int) -> Channels:
    return db.session.execute(select(Channels).filter_by(id=channel_id)).scalars().one()


def get_video(video_id: int) -> Video:
    return db.session.execute(select(Video).filter_by(id=video_id)).scalars().one()


def get_video_by_channel(channel_id: int) -> Sequence[Video] | None:
    return (
        db.session.execute(select(Video).filter_by(channel_id=channel_id))
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
            transcriptions += video.transcriptions
    return transcriptions


def search_wordmaps_by_transcription(
    search_term: str, transcription: Transcription
) -> Sequence[WordMaps]:
    return (
        db.session.execute(
            select(WordMaps).filter_by(
                transcription_id=transcription.id, word=search_term
            )
        )
        .scalars()
        .all()
    )


def get_segments_by_wordmap(wordmap: WordMaps) -> Sequence[Segments]:
    return db.session.query(Segments).filter(Segments.id.in_(wordmap.segments)).all()


def get_segment_by_id(segment_id: int) -> Segments:
    return db.session.query(Segments).filter_by(id=segment_id).one()


def delete_channel(channel_id: int):
    return db.session.query(Channels).filter_by(id=channel_id).delete()


def delete_broadcaster(broadcaster_id: int):
    return db.session.query(Broadcaster).filter_by(id=broadcaster_id).delete()


def delete_wordmaps_on_transcription(transcription_id: int):

    logger.info(f"delete wordmaps on transcription id: {transcription_id}")
    return (
        db.session.query(WordMaps).filter_by(transcription_id=transcription_id).delete()
    )


def fetch_transcription(video_id: int):
    video = get_video(video_id)
    video_url = video.get_url()
    if video_url is not None:
        logger.info(f"fetching transcription for {video_url}")
        subtitles, parsedDate = get_yt_video_subtitles(video_url)
        for sub in subtitles:
            logger.info(
                f"checking if transcriptions exists on {video_id}, {len(video.transcriptions)}"
            )
            if parsedDate is not None:
                video.uploaded = parsedDate
            if len(video.transcriptions) == 0:
                logger.info(f"transcriptions not found on {video_id}, adding new..")
                db.session.add(
                    Transcription(
                        video_id=video_id,
                        language=sub.language,
                        file_extention=sub.extention,
                        file=open(sub.path, "rb"),
                        source=TranscriptionSource.YouTube,
                    )
                )
            else:
                logger.info(f"transcriptions found on {video_id}, updating existing..")
                for t in video.transcriptions:
                    logger.info(
                        f"transcriptions found on {video_id} with platform {t.source}"
                    )
                    if t.source == TranscriptionSource.YouTube:
                        t.file = open(sub.path, "rb")
                        t.file_extention = sub.extention
                        t.language = sub.language
                        t.last_updated = datetime.now()

        db.session.commit()


def fetch_audio(video_id: int):
    video = get_video(video_id)
    video_url = video.get_url()
    if video.audio is None:
        if video_url is not None:
            logger.info(f"fetching audio for {video_url}")
            audio = get_yt_audio(video_url)
            logger.info(f"adding audio on {video_id}..")
            video.audio = open(audio, "rb")
            db.session.commit()
    else:
        logger.info(f"skipped audio for {video_url}, already exists.")
