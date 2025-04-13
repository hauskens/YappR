import logging
from collections.abc import Sequence
from sqlalchemy import select
from flask_discord.models import User
from .models.db import (
    Broadcaster,
    Permissions,
    Platforms,
    Segments,
    WordMaps,
    Channels,
    Video,
    Transcription,
    TranscriptionSource,
    Logs,
    Users,
    AccountSource,
    PermissionType,
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
            transcriptions += video.transcriptions
    return transcriptions


def get_transcriptions_on_channels_daterange(
    channels: Sequence[Channels], start_date: datetime, end_date: datetime
) -> Sequence[Transcription]:
    transcriptions: list[Transcription] = []
    for channel in channels:
        for video in channel.videos:
            logger.debug(f"Checking DATE: {start_date} < {video.uploaded} < {end_date}")
            if start_date <= video.uploaded <= end_date:
                transcriptions += video.transcriptions
                logger.debug("Found match!")
    return transcriptions


def get_valid_date(date_string: str) -> datetime | None:
    try:
        date = datetime.strptime(date_string, "%Y-%m-%d")
        return date
    except ValueError:
        logger.warning(f"didnt match date on {date_string}")
        return


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


def delete_broadcaster(broadcaster_id: int):
    return db.session.query(Broadcaster).filter_by(id=broadcaster_id).delete()


def delete_wordmaps_on_transcription(transcription_id: int):

    logger.info(f"delete wordmaps on transcription id: {transcription_id}")
    return (
        db.session.query(WordMaps).filter_by(transcription_id=transcription_id).delete()
    )


def get_users() -> list[Users]:
    return db.session.query(Users).all()


def get_stats_videos() -> int:
    return db.session.query(Video.id).count()


def get_stats_words() -> int:
    return db.session.query(WordMaps.word).count()


def get_stats_segments() -> int:
    return db.session.query(Segments.id).count()


def get_user_permissions(user: Users) -> list[Permissions]:
    return db.session.query(Permissions).filter_by(user_id=user.id).all()


def get_user_by_ext(user_external_id: str) -> Users:
    return db.session.query(Users).filter_by(external_account_id=user_external_id).one()


def get_user_by_id(user_id: int) -> Users:
    return db.session.query(Users).filter_by(id=user_id).one()


def get_permissions_by_ext(user_external_id: str) -> list[Permissions]:
    user = get_user_by_ext(user_external_id)
    return db.session.query(Permissions).filter_by(user_id=user.id).all()


def has_permissions_by_ext(
    user_external_id: str, permission_type: PermissionType
) -> bool:
    permissions = get_permissions_by_ext(user_external_id)
    for p in permissions:
        if p.permission_type == permission_type:
            return True
    return False


def add_permissions(user: Users, permission_type: PermissionType):
    existing_permissions = (
        db.session.query(Permissions)
        .filter_by(user_id=user.id, permission_type=permission_type)
        .one_or_none()
    )
    if existing_permissions is None:
        db.session.add(Permissions(user_id=user.id, permission_type=permission_type))
        logger.info(f"Granted {permission_type.name} {user.name}!")
        db.session.commit()


def add_user(user: User):
    existing_user = db.session.query(Users).filter_by(external_account_id=str(user.id))
    if existing_user.one_or_none() is None:
        db.session.add(
            Users(
                name=str(user.username),
                external_account_id=str(user.id),
                account_type=AccountSource.Discord,
            )
        )
        logger.info(f"User created for {user.username}!")
    else:
        existing_user.one().last_login = datetime.now()
    db.session.commit()


def add_log(log_text: str):
    logger.info(log_text)
    db.session.add(Logs(text=log_text))
    db.session.commit()


def fetch_transcription(video_id: int):
    video = get_video(video_id)
    video_url = video.get_url()
    if video_url is not None:
        logger.info(f"fetching transcription for {video_url}")
        subtitles, parsedDate = get_yt_video_subtitles(video_url)
        if parsedDate is not None:
            video.uploaded = parsedDate
        for sub in subtitles:
            logger.info(
                f"checking if transcriptions exists on {video_id}, {len(video.transcriptions)}"
            )
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
