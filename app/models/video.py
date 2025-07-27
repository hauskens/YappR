from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy_file import FileField, File
from datetime import datetime
from .base import Base
from .enums import VideoType


class Video(Base):
    __tablename__: str = "video"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250))
    video_type: Mapped[VideoType] = mapped_column(Enum(VideoType))
    duration: Mapped[float] = mapped_column(Float())
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id"), index=True)
    channel: Mapped["Channels"] = relationship() # type: ignore[name-defined]
    source_video_id: Mapped[int | None] = mapped_column(
        ForeignKey("video.id"), index=True, nullable=True
    )
    source_video: Mapped["Video"] = relationship(
        back_populates="video_refs", remote_side="Video.id"
    )
    video_refs: Mapped[list["Video"]] = relationship(
        back_populates="source_video")
    last_updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now())
    uploaded: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime(1970, 1, 1)
    )
    platform_ref: Mapped[str] = mapped_column(String(), unique=True)
    active: Mapped[bool] = mapped_column(Boolean(), default=True)
    thumbnail: Mapped[File | None] = mapped_column(
        FileField(upload_storage="thumbnails"))
    audio: Mapped[File | None] = mapped_column(FileField())
    transcriptions: Mapped[list["Transcription"]] = relationship( # type: ignore[name-defined]
        back_populates="video", cascade="all, delete-orphan"
    )

#     def delete(self):
#         for t in self.transcriptions:
#             t.delete()
#         _ = db.session.query(Video).filter_by(id=self.id).delete()
#         db.session.commit()

#     def get_duration_str(self) -> str:
#         return seconds_to_string(self.duration)

#     def get_url(self) -> str:
#         url = self.channel.platform.url
#         if self.channel.platform.name.lower() == "youtube":
#             return f"{url}/watch?v={self.platform_ref}"
#         elif self.channel.platform.name.lower() == "twitch":
#             return f"{url}/videos/{self.platform_ref}"
#         raise ValueError(f"Could not generate url for video: {self.id}")

#     def get_url_with_timestamp(self, seconds_offset: float) -> str:
#         """Generate a URL to the video at a specific timestamp.

#         Args:
#             seconds_offset: Number of seconds from the start of the video

#         Returns:
#             URL string with appropriate timestamp format for the platform
#         """
#         base_url = self.get_url()

#         # Ensure seconds_offset is positive and within video duration
#         seconds_offset = max(0, min(seconds_offset, self.duration))

#         # Format timestamp based on platform
#         if self.channel.platform.name.lower() == "youtube":
#             # YouTube uses t=123s format (seconds)
#             return f"{base_url}&t={int(seconds_offset)}s"
#         elif self.channel.platform.name.lower() == "twitch":
#             # Twitch uses t=01h23m45s format
#             hours = int(seconds_offset // 3600)
#             minutes = int((seconds_offset % 3600) // 60)
#             seconds = int(seconds_offset % 60)

#             if hours > 0:
#                 timestamp = f"{hours:02d}h{minutes:02d}m{seconds:02d}s"
#             else:
#                 timestamp = f"{minutes:02d}m{seconds:02d}s"

#             return f"{base_url}?t={timestamp}"

#         # Default fallback
#         return base_url

#     def archive(self):
#         for video in self.video_refs:
#             if video.video_type == VideoType.VOD:
#                 for transcription in self.transcriptions:
#                     transcription.video_id = video.id
#                     logger.info(
#                         f"Transcription id: {transcription.id} on video id{self.id} is transfered to {video.id}"
#                     )
#                 db.session.commit()


#     def download_transcription(self, force: bool = False):
#         if force:
#             for t in self.transcriptions:
#                 if t.source == TranscriptionSource.YouTube:
#                     logger.info(
#                         f"transcriptions found {self.platform_ref}, forcing delete"
#                     )
#                     db.session.delete(t)
#             db.session.commit()
#         if len(self.transcriptions) == 0:
#             logger.info(
#                 f"transcriptions not found on {self.platform_ref}, adding new.."
#             )
#             formatter = WebVTTFormatter()
#             path = config.cache_location + self.platform_ref + ".vtt"
#             transcription = fetch_transcription(self.platform_ref)
#             t_formatted = formatter.format_transcript(transcription)
#             with open(path, "w", encoding="utf-8") as vtt_file:
#                 _ = vtt_file.write(t_formatted)
#             db.session.add(
#                 Transcription(
#                     video_id=self.id,
#                     language=transcription.language,
#                     file_extention="vtt",
#                     file=open(path, "rb"),
#                     source=TranscriptionSource.YouTube,
#                 )
#             )
#             db.session.commit()

#     def process_transcriptions(self, force: bool = False):
#         transcription_to_process: Transcription | None = None
#         for t in self.transcriptions:
#             if force:
#                 t.reset()
#             if len(self.transcriptions) == 1:
#                 transcription_to_process = t
#             if (
#                 len(self.transcriptions) > 1
#                 and t.source is not TranscriptionSource.YouTube
#             ):
#                 transcription_to_process = t
#             if len(self.transcriptions) > 1 and t.source is TranscriptionSource.YouTube:
#                 t.reset()

#         logger.info(
#             f"Processing transcriptions for {self.id}, found {transcription_to_process}"
#         )
#         if transcription_to_process is not None:
#             transcription_to_process.reset()
#             transcription_to_process.process_transcription(force)

#     def save_audio(self, force: bool = False):
#         if (
#             self.channel.platform.name.lower() == "twitch"
#         ):
#             audio = get_twitch_audio(self.get_url())
#             self.audio = open(audio, "rb")  # type: ignore
#             db.session.commit()
#         if (
#             self.channel.platform.name.lower() == "youtube"
#         ):
#             audio = get_yt_audio(self.get_url())
#             self.audio = open(audio, "rb")  # type: ignore
#             db.session.commit()
