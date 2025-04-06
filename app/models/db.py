import enum
from sqlalchemy import (
    ForeignKey,
    String,
    Integer,
    Enum,
    Float,
    UniqueConstraint,
    DateTime,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.mutable import MutableList
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
        url = self.platform.url
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


# # todo: test if this works..
# @event.listens_for(Video, "before_insert")
# def receive_before_insert(mapper, connection, target):
#     target.last_updated = datetime.now()
#
#
# @event.listens_for(Video, "before_update")
# def receive_before_insert(mapper, connection, target):
#     target.last_updated = datetime.now()


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
    processed_transcription: Mapped["ProcessedTranscription"] = relationship(
        back_populates="transcription", cascade="all, delete-orphan"
    )


# @event.listens_for(Transcription, "before_insert")
# def receive_before_insert(mapper, connection, target):
#     target.last_updated = datetime.now()
#
#
# @event.listens_for(Transcription, "before_update")
# def receive_before_insert(mapper, connection, target):
#     target.last_updated = datetime.now()


class Segments(Base):
    __tablename__: str = "t_segments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    time: Mapped[int] = mapped_column(Integer, nullable=False)
    processed_transcription_id: Mapped[int] = mapped_column(
        ForeignKey("t_processed.id")
    )
    processed_transcription: Mapped["ProcessedTranscription"] = relationship()


class WordMaps(Base):
    __tablename__: str = "t_wordmaps"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    word: Mapped[str] = mapped_column(String(50))
    segments: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    processed_transcription_id: Mapped[int] = mapped_column(
        ForeignKey("t_processed.id")
    )
    processed_transcription: Mapped["ProcessedTranscription"] = relationship()


class ProcessedTranscription(Base):
    __tablename__: str = "t_processed"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transcription_id: Mapped[int] = mapped_column(
        ForeignKey("transcriptions.id"), unique=True
    )
    transcription: Mapped["Transcription"] = relationship()
    segments: Mapped[list["Segments"]] = relationship(
        back_populates="processed_transcription", cascade="all, delete-orphan"
    )
    word_maps: Mapped[list["WordMaps"]] = relationship(
        back_populates="processed_transcription", cascade="all, delete-orphan"
    )

    #
    #
    # {
    #     "id": 123,
    #     "segments": segments,
    #     "word_map": word_map,
    #     "full_text": full_text,
    #     "idx_to_time": idx_to_time,
    #     "upload_date": "todaylol",
    # }
