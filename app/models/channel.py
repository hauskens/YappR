from sqlalchemy import String, ForeignKey, DateTime, Integer, Boolean, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base
from .enums import VideoType, PlatformType
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
        ForeignKey("channels.id"), index=True, nullable=True
    )
    source_channel: Mapped["Channels"] = relationship()
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


#     def link_to_channel(self, channel_id: int | None = None):
#         if channel_id is not None:
#             try:
#                 target_channel = (
#                     db.session.query(Channels)
#                     .filter_by(id=channel_id, broadcaster_id=self.broadcaster_id)
#                     .one()
#                 )
#                 self.source_channel_id = (
#                     target_channel.id
#                 )  # I could have just taken channel_id directly from function, but this is to validate that it exists on broadcaster
#                 db.session.commit()
#             except:
#                 raise ValueError(
#                     "Failed to find target channel on broadcaster, is the broadcaster the same?"
#                 )
#         else:
#             self.source_channel_id = None
#             db.session.commit()

#     def look_for_linked_videos(self, margin_sec: int = 2, min_duration: int = 300):
#         logger.info(f"Looking for potential links on channel {self.name}")
#         for source_video in self.source_channel.videos:
#             for target_video in self.videos:
#                 if (
#                     target_video.source_video_id is None
#                     and target_video.duration > min_duration
#                     and (
#                         (source_video.duration - margin_sec)
#                         <= target_video.duration
#                         <= (source_video.duration + margin_sec)
#                     )
#                 ):
#                     logger.info(
#                         f"Found a match on video duration! Source: {source_video.id} -> target: {target_video.id}"
#                     )
#                     target_video.source_video_id = source_video.id
#                     db.session.flush()
#         db.session.commit()

class ChannelEvent(Base):
    __tablename__ = "channel_events"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"))
    channel: Mapped["Channels"] = relationship()

    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    raw_message: Mapped[str] = mapped_column(String(512), nullable=False)


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
