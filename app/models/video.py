from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy_file import FileField, File
from datetime import datetime
from typing import Annotated
from pydantic import BaseModel, Field, HttpUrl
from .base import Base
from .enums import VideoType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .channel import Channels
    from .transcription import Transcription
    from .timestamp_mapping import TimestampMapping


class VideoDetails(BaseModel):
    """Pydantic model for video creation."""
    title: str
    video_type: VideoType
    duration: Annotated[float, Field(gt=0)]
    platform_ref: str
    uploaded: datetime
    active: bool = True
    thumbnail_url: HttpUrl


class VideoCreate(VideoDetails):
    channel_id: int


class Video(Base):
    __tablename__: str = "video"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250))
    video_type: Mapped[VideoType] = mapped_column(Enum(VideoType))
    duration: Mapped[float] = mapped_column(Float())
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id"), index=True)
    channel: Mapped["Channels"] = relationship()
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
    transcriptions: Mapped[list["Transcription"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    source_mappings: Mapped[list["TimestampMapping"]] = relationship(
        foreign_keys="[TimestampMapping.source_video_id]",
        back_populates="source_video",
        cascade="all, delete-orphan"
    )
    target_mappings: Mapped[list["TimestampMapping"]] = relationship(
        foreign_keys="[TimestampMapping.target_video_id]",
        back_populates="target_video",
        cascade="all, delete-orphan"
    )
    estimated_upload_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    
    def is_linked_to_source(self) -> bool:
        """Check if this video is linked to any source video."""
        from app.services.video import VideoService
        return VideoService.is_linked_to_source(self)
    
    @property
    def source_video(self) -> "Video | None":
        """Property for backward compatibility with old source_video relationship."""
        from app.services.video import VideoService
        return VideoService.get_source_video(self)
    
    @property 
    def source_video_id(self) -> int | None:
        """Property for backward compatibility with old source_video_id field."""
        from app.services.video import VideoService
        return VideoService.get_source_video_id(self)
