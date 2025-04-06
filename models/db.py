import enum
from sqlalchemy import ForeignKey, String, Integer, Enum, Float
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy_file import FileField


class Base(DeclarativeBase):
    pass


class Broadcaster(Base):
    __tablename__: str = "broadcaster"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(250), unique=True)


class Platforms(Base):
    __tablename__: str = "platforms"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(250), unique=True)
    url: Mapped[str] = mapped_column(String(1000), unique=True)


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
    platform_ref: Mapped[str] = mapped_column(String(), unique=True)

    def get_url(self) -> str | None:
        url = self.channel.platform.url.rstrip("/")
        if self.channel.platform.name.lower() == "youtube":
            return f"{url}/watch?v={self.platform_ref}"


class Transcription(Base):
    __tablename__: str = "transcriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("video.id"))
    video: Mapped["Video"] = relationship()
    language: Mapped[str] = mapped_column(String(250))
    file_extention: Mapped[str] = mapped_column(String(10))
    file: Mapped[FileField] = mapped_column(FileField())
    source: Mapped[str] = mapped_column(
        Enum(TranscriptionSource), default=TranscriptionSource.Unknown
    )
