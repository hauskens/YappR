from sqlalchemy import Integer, ForeignKey, DateTime, Float, String, BigInteger, Enum, Boolean, UniqueConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base
from .enums import ContentQueueSubmissionSource
from datetime import datetime



class ContentQueueSubmission(Base):
    __tablename__ = "content_queue_submissions"
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True)
    content_queue_id: Mapped[int] = mapped_column(
        ForeignKey("content_queue.id"))
    content_queue: Mapped["ContentQueue"] = relationship(
        back_populates="submissions")
    content_id: Mapped[int] = mapped_column(ForeignKey("content.id"))
    content: Mapped["Content"] = relationship()
    user_id: Mapped[int] = mapped_column(ForeignKey("external_users.id"))
    user: Mapped["ExternalUser"] = relationship()
    submitted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    submission_source_type: Mapped[ContentQueueSubmissionSource] = mapped_column(
        Enum(ContentQueueSubmissionSource), nullable=False)
    submission_source_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    user_comment: Mapped[str | None] = mapped_column(
        String(256), nullable=True)


class Content(Base):
    __tablename__ = "content"
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    stripped_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(
        String(1000), nullable=True)
    channel_name: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, server_default=None)

    # def get_platform(self):
    #     return PlatformRegistry.get_handler_by_url(self.url).platform_name

    # def get_video_timestamp_url(self, timestamp: int):
    #     return PlatformRegistry.get_url_with_timestamp(self.url, timestamp)

class ContentQueue(Base):
    __tablename__ = "content_queue"
    __table_args__ = (
        UniqueConstraint("broadcaster_id", "content_id",
                         name="uq_broadcaster_content"),
    )
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True)
    broadcaster_id: Mapped[int] = mapped_column(ForeignKey("broadcaster.id"))
    broadcaster: Mapped["Broadcaster"] = relationship()
    content_id: Mapped[int] = mapped_column(ForeignKey("content.id"))
    content: Mapped["Content"] = relationship()
    content_timestamp: Mapped[int | None] = mapped_column(
        Integer, nullable=True, server_default=None)
    watched: Mapped[bool] = mapped_column(Boolean, default=False)
    watched_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)
    skipped: Mapped[bool] = mapped_column(Boolean, default=False)
    submissions: Mapped[list["ContentQueueSubmission"]
                        ] = relationship(back_populates="content_queue")
    score: Mapped[float] = mapped_column(Float, default=0, server_default='0')

    # @property
    # def total_weight(self) -> float:
    #     """Calculate the total weight of all related ContentQueueSubmission entries.
    #     This is a calculated property and not stored in the database.

    #     Returns:
    #         float: Sum of all submission weights, or 0 if there are no submissions
    #     """
    #     if not self.submissions:
    #         return 0.0
    #     return sum(submission.weight for submission in self.submissions)

    # def get_video_timestamp_url(self) -> str:
    #     if self.content_timestamp is None:
    #         raise ValueError("No timestamp on content")
    #     return PlatformRegistry.get_url_with_timestamp(self.content.url, self.content_timestamp)

    # def get_video_playable_url(self) -> str:
    #     if self.content_timestamp is None:
    #         return self.content.url
    #     return self.get_video_timestamp_url()

    # def get_vod_timestamp_url(self, time_shift: float = 60) -> str | None:
    #     """Find the broadcaster's video that was live when this clip was marked as watched
    #     and return a URL with the timestamp.

    #     The function finds the closest previous watched item with the same broadcaster_id
    #     and uses that time for the timestamp URL. If the time difference between this item
    #     and the previous one is longer than 90 seconds + video duration, it uses that instead.

    #     Args:
    #         time_shift: Default time shift in seconds (used as fallback if no previous item found)

    #     Returns:
    #         URL string with timestamp or None if no matching video found
    #     """
    #     if not self.watched or not self.watched_at:
    #         return None

    #     # Find the closest previous watched item with the same broadcaster_id
    #     previous_item = db.session.query(ContentQueue).filter(
    #         ContentQueue.broadcaster_id == self.broadcaster_id,
    #         ContentQueue.watched == True,
    #         ContentQueue.watched_at < self.watched_at
    #     ).order_by(ContentQueue.watched_at.desc()).first()
    #     # Calculate the time difference to use for the offset
    #     if previous_item and previous_item.watched_at:
    #         # Calculate time difference in seconds between current and previous item
    #         content_duration = self.content.duration or 0

    #         # Subtract content duration from the time difference
    #         time_diff = (self.watched_at -
    #                      previous_item.watched_at).total_seconds()

    #         # Ensure time_diff is at least 0
    #         time_diff = max(0, time_diff)

    #         # Use the minimum of the actual time difference and 90 seconds
    #         time_shift = min(time_diff, 90 + content_duration)

    #     # Find videos from this broadcaster's channels that were live when the clip was watched
    #     for channel in self.broadcaster.channels:
    #         # Look for videos that might include this timestamp
    #         # We need to find videos that were live when the clip was watched
    #         # SQLite doesn't have great datetime functions, so we'll fetch candidates and filter in Python
    #         candidate_videos = db.session.query(Video).filter(
    #             Video.channel_id == channel.id,
    #             Video.video_type == VideoType.VOD  # Ensure it's a VOD
    #         ).all()

    #         for video in candidate_videos:
    #             # Check if video was live when clip was watched
    #             video_end_time = video.uploaded + \
    #                 timedelta(seconds=video.duration)
    #             if video.uploaded <= self.watched_at <= video_end_time:
    #                 # Calculate seconds from start of video to when clip was watched
    #                 seconds_offset = (
    #                     self.watched_at - video.uploaded - timedelta(seconds=time_shift)).total_seconds()

    #                 # Generate URL with timestamp
    #                 return video.get_url_with_timestamp(seconds_offset)

    #     return None