import enum
from sqlalchemy import (
    Boolean,
    ForeignKey,
    String,
    Integer,
    Enum,
    Float,
    DateTime,
)
from flask_sqlalchemy import SQLAlchemy
from flask_dance.consumer.storage.sqla import OAuthConsumerMixin
from flask_login import UserMixin
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy_file import FileField, File
from sqlalchemy_file.storage import StorageManager
from datetime import datetime
from io import BytesIO
import logging
import webvtt
import re
from libcloud.storage.drivers.local import LocalStorageDriver
from .config import config
from ..utils import get_sec, sanitize_sentence, save_thumbnail
from ..youtube_api import (
    get_youtube_channel_details,
    get_videos_on_channel,
    get_videos,
    fetch_transcription,
)
from .youtube.search import SearchResultItem
from youtube_transcript_api.formatters import WebVTTFormatter

logger = logging.getLogger(__name__)


container = LocalStorageDriver(config.storage_location).get_container("transcriptions")
StorageManager.add_storage("default", container)


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


class Broadcaster(Base):
    __tablename__: str = "broadcaster"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(250), unique=True)
    channels: Mapped[list["Channels"]] = relationship(
        back_populates="broadcaster", cascade="all, delete-orphan"
    )


class Platforms(Base):
    __tablename__: str = "platforms"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(250), unique=True)
    url: Mapped[str] = mapped_column(String(1000), unique=True)
    logo_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class VideoType(enum.Enum):
    Unknown = "unknown"
    VOD = "vod"
    Clip = "clip"
    Edit = "edit"


class TranscriptionSource(enum.Enum):
    Unknown = "unknown"
    YouTube = "youtube"


class PermissionType(enum.Enum):
    Admin = "admin"
    Reader = "reader"


class AccountSource(enum.Enum):
    Discord = "discord"


class Users(Base, UserMixin):
    __tablename__: str = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(500))
    external_account_id: Mapped[str | None] = mapped_column(
        String(500), unique=True, nullable=True
    )
    account_type: Mapped[str] = mapped_column(Enum(AccountSource))
    first_login: Mapped[datetime] = mapped_column(DateTime, default=datetime.now())
    last_login: Mapped[datetime] = mapped_column(DateTime, default=datetime.now())
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    permissions: Mapped[list["Permissions"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def has_permission(self, permission_type: PermissionType) -> bool:
        return any(p.permission_type == permission_type for p in self.permissions)

    def add_permissions(self, permission_type: PermissionType):
        if not self.has_permission(permission_type):
            db.session.add(
                Permissions(user_id=self.id, permission_type=permission_type)
            )
            db.session.commit()
            logger.info(f"Granted {permission_type.name} to {self.name}!")


class Permissions(Base):
    __tablename__: str = "permissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    user: Mapped["Users"] = relationship()
    permission_type: Mapped[str] = mapped_column(
        Enum(PermissionType), default=PermissionType.Reader
    )
    date_added: Mapped[datetime] = mapped_column(DateTime, default=datetime.now())


class Channels(Base):
    __tablename__: str = "channels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(250))
    broadcaster_id: Mapped[int] = mapped_column(ForeignKey("broadcaster.id"))
    broadcaster: Mapped["Broadcaster"] = relationship()
    platform_id: Mapped[int] = mapped_column(ForeignKey("platforms.id"))
    platform: Mapped["Platforms"] = relationship()
    platform_ref: Mapped[str] = mapped_column(String(), unique=True)
    platform_channel_id: Mapped[str | None] = mapped_column(
        String(), unique=True, nullable=True
    )
    main_video_type: Mapped[str] = mapped_column(
        Enum(VideoType), default=VideoType.Unknown
    )
    videos: Mapped[list["Video"]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )

    def get_url(self) -> str | None:
        url = self.platform.url
        if self.platform.name.lower() == "youtube":
            return f"{url}/@{self.platform_ref}"

    def update(self):
        result = get_youtube_channel_details(self.platform_ref)
        self.platform_channel_id = result.id
        db.session.commit()

    def delete(self):
        _ = db.session.query(Channels).filter_by(id=self.id).delete()
        db.session.commit()

    def fetch_latest_videos(self):
        if (
            self.platform.name.lower() == "youtube"
            and self.platform_channel_id is not None
        ):
            latest_videos = get_videos_on_channel(self.platform_channel_id)
            videos_result: list[SearchResultItem] = []
            for search_result in latest_videos.items:
                existing_video = (
                    db.session.query(Video)
                    .filter_by(platform_ref=search_result.id.videoId)
                    .one_or_none()
                )
                if existing_video is None:
                    videos_result.append(search_result)

            videos_details = get_videos([item.id.videoId for item in videos_result])
            for video in videos_details:
                tn = save_thumbnail(video)
                db.session.add(
                    Video(
                        title=video.snippet.title,
                        video_type=VideoType.VOD,
                        channel_id=self.id,
                        platform_ref=video.id,
                        duration=video.contentDetails.duration.total_seconds(),
                        uploaded=video.snippet.publishedAt,
                        thumbnail=open(tn, "rb"),
                    )
                )
        db.session.commit()


class Video(Base):
    __tablename__: str = "video"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250))
    video_type: Mapped[str] = mapped_column(Enum(VideoType))
    duration: Mapped[float] = mapped_column(Float())
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), index=True)
    channel: Mapped["Channels"] = relationship()
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.now())
    uploaded: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime(1970, 1, 1)
    )
    platform_ref: Mapped[str] = mapped_column(String(), unique=True)
    thumbnail: Mapped[File | None] = mapped_column(FileField())
    audio: Mapped[File | None] = mapped_column(FileField())
    transcriptions: Mapped[list["Transcription"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )

    def get_url(self) -> str | None:
        url = self.channel.platform.url
        if self.channel.platform.name.lower() == "youtube":
            return f"{url}/watch?v={self.platform_ref}"

    def fetch_details(self):
        result = get_videos([self.platform_ref])[0]
        self.duration = result.contentDetails.duration.total_seconds()
        self.title = result.snippet.title
        self.uploaded = result.snippet.publishedAt
        if self.thumbnail is None:
            tn = save_thumbnail(result)
            self.thumbnail = open(tn, "rb")
        db.session.commit()

    def save_transcription(self, force: bool = False):
        if force:
            for t in self.transcriptions:
                logger.info(f"transcriptions found {self.platform_ref}, forcing delete")
                db.session.delete(t)
            db.session.commit()
        if len(self.transcriptions) == 0:
            logger.info(
                f"transcriptions not found on {self.platform_ref}, adding new.."
            )
            formatter = WebVTTFormatter()
            path = config.cache_location + self.platform_ref + ".vtt"
            transcription = fetch_transcription(self.platform_ref)
            t_formatted = formatter.format_transcript(transcription)
            with open(path, "w", encoding="utf-8") as vtt_file:
                _ = vtt_file.write(t_formatted)
            db.session.add(
                Transcription(
                    video_id=self.id,
                    language=transcription.language,
                    file_extention="vtt",
                    file=open(path, "rb"),
                    source=TranscriptionSource.YouTube,
                )
            )
            db.session.commit()


class Transcription(Base):
    __tablename__: str = "transcriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("video.id"), index=True)
    video: Mapped["Video"] = relationship()
    language: Mapped[str] = mapped_column(String(250))
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.now())
    file_extention: Mapped[str] = mapped_column(String(10))
    file: Mapped[File] = mapped_column(FileField())
    source: Mapped[TranscriptionSource] = mapped_column(
        Enum(TranscriptionSource), default=TranscriptionSource.Unknown
    )
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    segments: Mapped[list["Segments"]] = relationship(
        back_populates="transcription", cascade="all, delete-orphan"
    )
    word_maps: Mapped[list["WordMaps"]] = relationship(
        back_populates="transcription", cascade="all, delete-orphan"
    )

    def delete_attached_wordmaps(self):
        _ = db.session.query(WordMaps).filter_by(transcription_id=self.id).delete()
        self.processed = False
        db.session.commit()

    def process_transcription(self, force: bool = False):
        logger.info(f"Task queued, parsing transcription for {self.id}")
        if self.processed:
            logger.info(f"Transcription {self.id}, already processed.. skipping")
            return
        if len(self.word_maps) > 0:
            logger.debug(f"wordmaps already found on {self.id}")
            if force:
                self.delete_attached_wordmaps()
            else:
                self.processed = True
                db.session.commit()
                return
            db.session.flush()
        _ = self.parse_vtt()
        self.processed = True
        db.session.commit()

    def parse_vtt(self):
        logger.info(f"Processing vtt transcription: {self.id}")
        segments: list[Segments] = []
        word_map: list[WordMaps] = []
        content = BytesIO(self.file.file.read())
        previous = None
        for caption in webvtt.from_buffer(content):
            start = get_sec(caption.start)
            # remove annotations, such as [music]
            text = re.sub(r"\[.*?\]", "", caption.text).strip().lower()

            if "\n" in text:
                continue
            if text == "":
                continue
            if text == previous:
                continue

            segment = Segments(
                text=text,
                start=start,
                transcription_id=self.id,
                end=get_sec(caption.end),
            )
            db.session.add(segment)
            db.session.flush()
            previous = text
            segments.append(segment)
            # words = pos_tag(word_tokenize(text))
            words = sanitize_sentence(text)
            # words = text.split()
            for word in words:
                found_existing_word = False
                for wm in word_map:
                    if wm.word == word:
                        wm.segments.append(segment.id)
                        found_existing_word = True
                        break
                if found_existing_word == False:
                    word_map.append(
                        WordMaps(
                            word=word,
                            segments=[segment.id],
                            transcription_id=self.id,
                        )
                    )
        db.session.add_all(word_map)
        db.session.commit()
        logger.info(f"Done processing transcription: {self.id}")


class Logs(Base):
    __tablename__: str = "logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String(250))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now())


class Segments(Base):
    __tablename__: str = "segments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    start: Mapped[int] = mapped_column(Integer, nullable=False)
    end: Mapped[int] = mapped_column(Integer, nullable=False)
    transcription_id: Mapped[int] = mapped_column(
        ForeignKey("transcriptions.id"), index=True
    )
    transcription: Mapped["Transcription"] = relationship()


class WordMaps(Base):
    __tablename__: str = "wordmaps"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    word: Mapped[str] = mapped_column(String(50), index=True)
    segments: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    transcription_id: Mapped[int] = mapped_column(
        ForeignKey("transcriptions.id"), index=True
    )
    transcription: Mapped["Transcription"] = relationship()


class OAuth(OAuthConsumerMixin, Base):
    provider_user_id: Mapped[str] = mapped_column(
        String(256), unique=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    user: Mapped["Users"] = relationship()
