from sqlalchemy import String, ForeignKey, DateTime, Integer, Boolean, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base
from .enums import VideoType, PlatformType, ChannelEventType
from datetime import datetime
from typing import TYPE_CHECKING
from pydantic import BaseModel

if TYPE_CHECKING:
    from .video import Video
    from .user import Users
    from .broadcaster import Broadcaster


class ChannelCreate(BaseModel):
    name: str
    broadcaster_id: int
    platform_name: PlatformType
    platform_ref: str
    platform_channel_id: str
    source_channel_id: int | None = None
    main_video_type: VideoType = VideoType.Unknown


class ChannelPlatformDetails(BaseModel):
    platform_ref: str


class Channels(Base):
    __tablename__: str = "channels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(250))
    broadcaster_id: Mapped[int] = mapped_column(ForeignKey("broadcaster.id"))
    broadcaster: Mapped["Broadcaster"] = relationship()
    platform_name: Mapped[str] = mapped_column(String(250))
    platform_ref: Mapped[str] = mapped_column(String(), unique=True)
    platform_channel_id: Mapped[str] = mapped_column(
        String(), unique=True, nullable=False
    )
    source_channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id"), nullable=True
    )
    source_channel: Mapped["Channels | None"] = relationship(foreign_keys=[source_channel_id], remote_side=[id])
    main_video_type: Mapped[VideoType] = mapped_column(
        Enum(VideoType), default=VideoType.Unknown
    )
    videos: Mapped[list["Video"]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )
    settings: Mapped["ChannelSettings"] = relationship(
        back_populates="channel", uselist=False)
    moderators: Mapped[list["ChannelModerator"]] = relationship(
        back_populates="channel",
        cascade="all, delete-orphan"
    )
    last_active: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)



class ChannelEvent(Base):
    __tablename__ = "channel_events"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"))
    channel: Mapped["Channels"] = relationship()

    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    event_type: Mapped[ChannelEventType] = mapped_column(
        Enum(ChannelEventType), nullable=False)
    username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True)
    user: Mapped["Users | None"] = relationship()
    raw_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    import_id: Mapped[int | None] = mapped_column(
        ForeignKey("chatlog_imports.id"), nullable=True)


class ChannelModerator(Base):
    __tablename__: str = "channel_moderators"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    user: Mapped["Users"] = relationship(
        back_populates="channel_moderators")  # type: ignore[name-defined]
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"))
    channel: Mapped["Channels"] = relationship(back_populates="moderators")


class ChannelSettings(Base):
    __tablename__ = "channel_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id"), unique=True)
    content_queue_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    chat_collection_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False)
    channel: Mapped["Channels"] = relationship(back_populates="settings")
