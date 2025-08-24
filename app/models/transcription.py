from sqlalchemy import String, Integer, Boolean, Enum, DateTime, ForeignKey, Text, Computed, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pydantic import BaseModel
from .enums import TranscriptionSource
from .base import Base
from datetime import datetime
from sqlalchemy_file import FileField, File
from sqlalchemy_utils.types.ts_vector import TSVectorType  # type: ignore


class SingleSegment(BaseModel):
    """
    A single segment (up to multiple sentences) of a speech.
    """

    start: float
    end: float
    text: str


class TranscriptionResult(BaseModel):
    """
    A list of segments and word segments of a speech.
    """

    segments: list[SingleSegment]
    language: str


class Transcription(Base):
    __tablename__: str = "transcriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("video.id"), index=True)
    video: Mapped["Video"] = relationship()  # type: ignore[name-defined]
    language: Mapped[str] = mapped_column(String(250))
    last_updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now())
    file_extention: Mapped[str] = mapped_column(String(10))
    file: Mapped[File] = mapped_column(FileField())
    source: Mapped[TranscriptionSource] = mapped_column(
        Enum(TranscriptionSource), default=TranscriptionSource.Unknown
    )
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    segments: Mapped[list["Segments"]] = relationship(
        back_populates="transcription", cascade="all, delete-orphan"
    )


class Segments(Base):
    __tablename__: str = "segments"
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_tsv: Mapped[TSVectorType] = mapped_column(
        TSVectorType("text", regconfig="simple"),
        Computed("to_tsvector('simple', \"text\")", persisted=True),
    )
    start: Mapped[int] = mapped_column(Integer, nullable=False)
    end: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_segment_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True)
    next_segment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transcription_id: Mapped[int] = mapped_column(
        ForeignKey("transcriptions.id"), index=True
    )
    transcription: Mapped["Transcription"] = relationship()


# Define GIN index for optimal full-text search performance
# Note: transcription_id already has a btree index from the ForeignKey definition
Index('ix_segments_text_tsv_gin', Segments.text_tsv, postgresql_using='gin')
