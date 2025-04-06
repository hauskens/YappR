import enum
from sqlalchemy import (
    ForeignKey,
    String,
    Integer,
    Enum,
    Float,
    UniqueConstraint,
    DateTime,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy_file import FileField
from sqlalchemy_file import File
from datetime import datetime


class Base(DeclarativeBase):
    pass


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


class Channels(Base):
    __tablename__: str = "channels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(250))
    broadcaster_id: Mapped[str] = mapped_column(ForeignKey("broadcaster.id"))
    broadcaster: Mapped["Broadcaster"] = relationship()
    platform_id: Mapped[int] = mapped_column(ForeignKey("platforms.id"))
    platform: Mapped["Platforms"] = relationship()
    platform_ref: Mapped[str] = mapped_column(String(), unique=True)
    main_video_type: Mapped[str] = mapped_column(
        Enum(VideoType), default=VideoType.Unknown
    )
    videos: Mapped[list["Video"]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )

    def get_url(self) -> str | None:
        url = self.platform.url.rstrip("/")
        if self.platform.name.lower() == "youtube":
            return f"{url}/@{self.platform_ref}"


class Video(Base):
    __tablename__: str = "video"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250))
    video_type: Mapped[str] = mapped_column(Enum(VideoType))
    duration: Mapped[float] = mapped_column(Float())
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"))
    channel: Mapped["Channels"] = relationship()
    last_updated: Mapped[DateTime] = mapped_column(DateTime, default=datetime.now())
    platform_ref: Mapped[str] = mapped_column(String(), unique=True)
    transcriptions: Mapped[list["Transcription"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )

    def get_url(self) -> str | None:
        url = self.channel.platform.url.rstrip("/")
        if self.channel.platform.name.lower() == "youtube":
            return f"{url}/watch?v={self.platform_ref}"


# todo: test if this works..
@event.listens_for(Video, "before_insert")
def receive_before_insert(mapper, connection, target):
    target.last_updated = datetime.now()


@event.listens_for(Video, "before_update")
def receive_before_insert(mapper, connection, target):
    target.last_updated = datetime.now()


class Transcription(Base):
    __tablename__: str = "transcriptions"
    __table_args__ = tuple(
        UniqueConstraint("video_id", "source", name="unique_video_source")
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("video.id"))
    video: Mapped["Video"] = relationship()
    language: Mapped[str] = mapped_column(String(250))
    last_updated: Mapped[DateTime] = mapped_column(DateTime, default=datetime.now())
    file_extention: Mapped[str] = mapped_column(String(10))
    file: Mapped[File] = mapped_column(FileField())
    source: Mapped[TranscriptionSource] = mapped_column(
        Enum(TranscriptionSource), default=TranscriptionSource.Unknown
    )


@event.listens_for(Transcription, "before_insert")
def receive_before_insert(mapper, connection, target):
    target.last_updated = datetime.now()


@event.listens_for(Transcription, "before_update")
def receive_before_insert(mapper, connection, target):
    target.last_updated = datetime.now()
