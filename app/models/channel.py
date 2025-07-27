from sqlalchemy import String, ForeignKey, DateTime, Integer, Boolean, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base
from .enums import VideoType
from datetime import datetime

class Channels(Base):
    __tablename__: str = "channels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(250))
    broadcaster_id: Mapped[int] = mapped_column(ForeignKey("broadcaster.id"))
    broadcaster: Mapped["Broadcaster"] = relationship() # type: ignore[name-defined]
    platform_id: Mapped[int] = mapped_column(ForeignKey("platforms.id"))
    platform: Mapped["Platforms"] = relationship() # type: ignore[name-defined]
    platform_ref: Mapped[str] = mapped_column(String(), unique=True)
    platform_channel_id: Mapped[str | None] = mapped_column(
        String(), unique=True, nullable=True
    )
    source_channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id"), index=True, nullable=True
    )
    source_channel: Mapped["Channels"] = relationship()
    main_video_type: Mapped[str] = mapped_column(
        Enum(VideoType), default=VideoType.Unknown
    )
    videos: Mapped[list["Video"]] = relationship( # type: ignore[name-defined]
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

#     def update_thumbnail(self):
#         for video in self.videos:
#             if video.thumbnail is None:
#                 video.fetch_details(force=True)

#     def get_url(self) -> str:
#         url = self.platform.url
#         if self.platform.name.lower() == "youtube":
#             return f"{url}/@{self.platform_ref}"
#         elif self.platform.name.lower() == "twitch":
#             return f"{url}/{self.platform_ref}"
#         raise ValueError(f"Could not generate url for channel: {self.id}")

#     def update(self):
#         if self.platform.name.lower() == "youtube":
#             result = get_youtube_channel_details(self.platform_ref)
#             self.platform_channel_id = result.id
#         elif self.platform.name.lower() == "twitch":
#             result = asyncio.run(get_twitch_user(self.platform_ref))
#             self.platform_channel_id = result.id
#         db.session.commit()

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

#     def delete(self):
#         for video in self.videos:
#             video.delete()
#         db.session.query(ChatLog).filter_by(channel_id=self.id).delete()
#         db.session.query(ChannelSettings).filter_by(
#             channel_id=self.id).delete()
#         db.session.query(ChannelModerator).filter_by(
#             channel_id=self.id).delete()
#         if self.broadcaster_id is not None:
#             queue = db.session.query(ContentQueue).filter_by(
#                 broadcaster_id=self.broadcaster_id).all()
#             for q_item in queue:
#                 db.session.query(ContentQueueSubmission).filter_by(
#                     content_queue_id=q_item.id).delete()
#             db.session.query(ContentQueue).filter_by(
#                 broadcaster_id=self.broadcaster_id).delete()

#         _ = db.session.query(Channels).filter_by(id=self.id).delete()
#         db.session.commit()

#     def process_videos(self, force: bool = False):
#         for video in self.videos:
#             video.process_transcriptions(force)

#     def download_audio_videos(self, force: bool = False):
#         for video in self.videos:
#             video.save_audio(force)

#     def get_videos_sorted_by_uploaded(self, descending: bool = True) -> list["Video"]:
#         return sorted(self.videos, key=lambda v: v.uploaded, reverse=descending)

#     def get_videos_sorted_by_id(self, descending: bool = True) -> list["Video"]:
#         return sorted(self.videos, key=lambda v: v.id, reverse=descending)

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

#     def fetch_videos_all(self):
#         if self.platform.name.lower() != "youtube":
#             return

#         latest_video_batches = get_all_videos_on_channel(
#             self.platform_channel_id)

#         video_id_set = set()
#         for item in latest_video_batches:
#             video_id = item.id.videoId
#             logger.info(f"Checking for existing video ref: {video_id}")
#             existing_video = (
#                 db.session.query(Video)
#                 .filter_by(platform_ref=video_id)
#                 .one_or_none()
#             )
#             if existing_video is None:
#                 logger.info(f"New video found: {video_id}")
#                 video_id_set.add(video_id)
#         if not video_id_set:
#             logger.info("No new videos found.")
#             return

#         video_details = get_videos(list(video_id_set))

#         for video in video_details:
#             try:
#                 tn = save_yt_thumbnail(video, force=True)
#                 db.session.add(
#                     Video(
#                         title=video.snippet.title,
#                         video_type=VideoType.VOD,
#                         channel_id=self.id,
#                         platform_ref=video.id,
#                         duration=video.contentDetails.duration.total_seconds(),
#                         uploaded=video.snippet.publishedAt,
#                         thumbnail=open(tn, "rb"),
#                     )
#                 )
#             except Exception as e:
#                 logger.error(f"Failed to add video {video.id}, exception: {e}")
#                 continue
#             db.session.flush()

#         db.session.commit()

#     def fetch_latest_videos(self, process: bool = False) -> int | None:
#         if (
#             self.platform.name.lower() == "youtube" and self.platform_channel_id is not None
#         ):
#             latest_videos = get_videos_on_channel(self.platform_channel_id)
#             videos_result: list[SearchResultItem] = []
#             for search_result in latest_videos.items:
#                 existing_video = (
#                     db.session.query(Video)
#                     .filter_by(platform_ref=search_result.id.videoId)
#                     .one_or_none()
#                 )
#                 if existing_video is None:
#                     videos_result.append(search_result)

#             videos_details = get_videos(
#                 [item.id.videoId for item in videos_result])
#             for video in videos_details:
#                 tn = save_yt_thumbnail(video, force=True)
#                 db.session.add(
#                     Video(
#                         title=video.snippet.title,
#                         video_type=VideoType.VOD,
#                         channel_id=self.id,
#                         platform_ref=video.id,
#                         duration=video.contentDetails.duration.total_seconds(),
#                         uploaded=video.snippet.publishedAt,
#                         thumbnail=open(tn, "rb"),
#                     )
#                 )
#             db.session.commit()
#         elif (
#             self.platform.name.lower() == "twitch" and self.platform_channel_id is not None
#         ):
#             logger.info(
#                 f"Fetching latest videos for twitch channel: {self.name} - Process: {process}")
#             limit = 1 if process else 100
#             twitch_latest_videos = asyncio.run(
#                 get_latest_broadcasts(self.platform_channel_id, limit=limit)
#             )
#             for video_data in twitch_latest_videos:
#                 logger.info(
#                     f"Processing video ref: {video_data.id} - got {len(twitch_latest_videos)} videos")

#                 # Query full DB, not just self.videos
#                 existing_video = (
#                     db.session.query(Video)
#                     .filter_by(platform_ref=video_data.id)
#                     .one_or_none()
#                 )

#                 if existing_video is None:
#                     tn = save_twitch_thumbnail(video_data, force=True)
#                     logger.info(f"Found new video ref: {video_data.id}")
#                     vid = Video(
#                         title=video_data.title,
#                         video_type=VideoType.VOD,
#                         channel_id=self.id,
#                         platform_ref=video_data.id,
#                         duration=parse_time(video_data.duration),
#                         uploaded=video_data.created_at,
#                         thumbnail=open(tn, "rb"),
#                         active=True,
#                     )
#                     db.session.add(vid)
#                     if process:
#                         db.session.commit()
#                         return db.session.query(Video).filter_by(platform_ref=video_data.id).one().id
#                 else:
#                     try:
#                         tn = save_twitch_thumbnail(video_data, force=True)
#                         logger.info(
#                             f"Updating existing video: {video_data.id}")
#                         existing_video.thumbnail = open(
#                             tn, "rb")  # type: ignore
#                         existing_video.active = True
#                         existing_video.title = video_data.title
#                         existing_video.uploaded = video_data.created_at
#                         db.session.flush()
#                         if abs(existing_video.duration - parse_time(video_data.duration)) > 1:
#                             logger.info(
#                                 f"Duration changed for video {self.platform_ref}: {existing_video.duration} -> {parse_time(video_data.duration)}"
#                             )
#                             for transcription in existing_video.transcriptions:
#                                 transcription.delete()
#                             try:
#                                 if existing_video.audio is not None:
#                                     existing_video.audio.file.object.delete()
#                             except Exception as e:
#                                 logger.error(
#                                     f"Failed to delete audio for video {self.platform_ref}, exception: {e}")
#                             existing_video.audio = None
#                             existing_video.duration = parse_time(
#                                 video_data.duration)
#                         if process:
#                             return existing_video.id
#                         if existing_video.channel_id != self.id:
#                             existing_video.channel_id = self.id
#                         db.session.flush()
#                     except Exception as e:
#                         logger.error(
#                             f"Failed to update video {video_data.id}, exception: {e}")
#                         continue
#         db.session.commit()
#         return None

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
    user: Mapped["Users"] = relationship(back_populates="channel_moderators") # type: ignore[name-defined]
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