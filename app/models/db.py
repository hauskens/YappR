import enum
from sqlalchemy import (
    ForeignKey,
    String,
    Integer,
    Enum,
    Float,
    DateTime,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, query
from sqlalchemy_file import FileField
from sqlalchemy_file import File
from datetime import datetime
import logging
from flask_dance.consumer.storage.sqla import OAuthConsumerMixin
from flask_login import UserMixin

logger = logging.getLogger(__name__)


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
    segments: Mapped[list["Segments"] | None] = relationship(
        back_populates="transcription", cascade="all, delete-orphan"
    )
    word_maps: Mapped[list["WordMaps"] | None] = relationship(
        back_populates="transcription", cascade="all, delete-orphan"
    )


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
