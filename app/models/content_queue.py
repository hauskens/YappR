from sqlalchemy import Integer, ForeignKey, DateTime, Float, String, BigInteger, Enum, Boolean, UniqueConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base
from .enums import ContentQueueSubmissionSource
from app.platforms.handler import PlatformRegistry
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .broadcaster import Broadcaster
    from .user import Users


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
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    user: Mapped["Users"] = relationship()
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

    def get_platform(self):
        return PlatformRegistry.get_handler_by_url(self.url).platform_name

    def get_video_timestamp_url(self, timestamp: int):
        return PlatformRegistry.get_url_with_timestamp(self.url, timestamp)


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

    @property
    def total_weight(self) -> float:
        """Calculate the total weight of all related ContentQueueSubmission entries.
        This is a calculated property and not stored in the database.

        Returns:
            float: Sum of all submission weights, or 0 if there are no submissions
        """
        if not self.submissions:
            return 0.0
        return sum(submission.weight for submission in self.submissions)

