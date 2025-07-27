from sqlalchemy import String, Integer, Boolean, Enum, DateTime, ForeignKey, Text, Computed
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
    video: Mapped["Video"] = relationship() # type: ignore[name-defined]
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

    # def delete(self):
    #     self.reset()
    #     _ = db.session.query(Transcription).filter_by(id=self.id).delete()
    #     db.session.commit()

    # def reset(self):
    #     self.delete_attached_segments()
    #     self.processed = False

    # def delete_attached_segments(self):
    #     _ = db.session.query(Segments).filter_by(
    #         transcription_id=self.id).delete()
    #     self.processed = False
    #     db.session.commit()

    # def get_segments_sorted(self, descending: bool = True) -> list["Segments"]:
    #     return sorted(self.segments, key=lambda v: v.start, reverse=not descending)

    # def process_transcription(self, force: bool = False):
    #     logger.info(
    #         f"Task queued, parsing transcription for {self.id}, - {force}")
    #     if self.processed and force == False and len(self.segments) == 0:
    #         logger.info(
    #             f"Transcription {self.id}, already processed.. skipping")
    #         return
    #     if force:
    #         self.reset()
    #     if self.file_extention == "vtt":
    #         _ = self.parse_vtt()
    #     elif self.file_extention == "json":
    #         _ = self.parse_json()
    #     self.processed = True
    #     db.session.commit()

    # def to_srt(self) -> str:
    #     """
    #     Convert the transcription to SRT format.

    #     Returns:
    #         str: The transcription in SRT format
    #     """
    #     if not self.processed:
    #         self.process_transcription()

    #     segments = self.get_segments_sorted()
    #     srt_content = convert_to_srt(segments)
    #     return srt_content

    # def to_json(self) -> str:
    #     """
    #     Convert the transcription to JSON format.

    #     Returns:
    #         str: The transcription in JSON format
    #     """
    #     if not self.processed:
    #         self.process_transcription()

    #     segments = self.get_segments_sorted()
    #     json_segments = []

    #     for segment in segments:
    #         json_segments.append({
    #             "text": segment.text,
    #             "start": segment.start,
    #             "end": segment.end
    #         })

    #     result = {
    #         "segments": json_segments,
    #         "language": self.language
    #     }

    #     return json.dumps(result, ensure_ascii=False)

    # def save_as_srt(self, output_path: str | None = None) -> str:
    #     """
    #     Convert the transcription to SRT format and save it to a file.

    #     Args:
    #         output_path: Path to save the SRT file. If None, a path will be generated
    #                     based on the video ID and transcription ID.

    #     Returns:
    #         str: Path to the saved SRT file
    #     """
    #     srt_content = self.to_srt()

    #     if output_path is None:
    #         # Generate a filename based on video ID and transcription ID
    #         output_path = f"transcription_{self.video_id}_{self.id}.srt"

    #     with open(output_path, "w", encoding="utf-8") as f:
    #         f.write(srt_content)

    #     logger.info(f"Saved SRT file to {output_path}")
    #     return output_path

    # def save_as_json(self, output_path: str | None = None) -> str:
    #     """
    #     Convert the transcription to JSON format and save it to a file.

    #     Args:
    #         output_path: Path to save the JSON file. If None, a path will be generated
    #                     based on the video ID and transcription ID.

    #     Returns:
    #         str: Path to the saved JSON file
    #     """
    #     json_content = self.to_json()

    #     if output_path is None:
    #         # Generate a filename based on video ID and transcription ID
    #         output_path = f"transcription_{self.video_id}_{self.id}.json"

    #     with open(output_path, "w", encoding="utf-8") as f:
    #         f.write(json_content)

    #     logger.info(f"Saved JSON file to {output_path}")
    #     return output_path

    # def parse_json(self):
    #     logger.info(f"Processing json transcription: {self.id}")
    #     segments: list[Segments] = []
    #     content = TranscriptionResult.model_validate_json(
    #         self.file.file.read().decode()
    #     )
    #     self.reset()

    #     previous_segment: Segments | None = None
    #     logger.info(f"Processing json transcription: {self.id}")
    #     for caption in content.segments:
    #         start = int(caption.start)
    #         if caption.text == "":
    #             continue
    #         if previous_segment is not None and caption.text == previous_segment.text:
    #             continue

    #         segment = Segments(
    #             text=caption.text,
    #             start=start,
    #             transcription_id=self.id,
    #             end=int(caption.end),
    #             previous_segment_id=(
    #                 previous_segment.id if previous_segment is not None else None
    #             ),
    #         )
    #         db.session.add(segment)
    #         db.session.flush()
    #         if previous_segment is not None:
    #             previous_segment.next_segment_id = segment.id
    #             db.session.add(previous_segment)
    #             db.session.flush()

    #         previous_segment = segment
    #         segments.append(segment)
    #     db.session.commit()
    #     logger.info(f"Done processing transcription: {self.id}")

    # def parse_vtt(self):
    #     logger.info(f"Processing vtt transcription: {self.id}")
    #     segments: list[Segments] = []
    #     content = BytesIO(self.file.file.read())
    #     previous_segment: Segments | None = None
    #     for caption in webvtt.from_buffer(content):
    #         start = get_sec(caption.start)
    #         # remove annotations, such as [music]
    #         text = re.sub(r"\[.*?\]", "", caption.text).strip().lower()

    #         if "\n" in text:
    #             continue
    #         if text == "":
    #             continue
    #         if previous_segment is not None and text == previous_segment.text:
    #             continue

    #         segment = Segments(
    #             text=text,
    #             start=start,
    #             transcription_id=self.id,
    #             end=get_sec(caption.end),
    #             previous_segment_id=(
    #                 previous_segment.id if previous_segment is not None else None
    #             ),
    #         )
    #         db.session.add(segment)
    #         db.session.flush()
    #         if previous_segment is not None:
    #             previous_segment.next_segment_id = segment.id
    #             db.session.add(previous_segment)
    #             db.session.flush()

    #         previous_segment = segment
    #         segments.append(segment)
    #     db.session.commit()
    #     logger.info(f"Done processing transcription: {self.id}")

class Segments(Base):
    __tablename__: str = "segments"
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_tsv: Mapped[TSVectorType] = mapped_column(
        TSVectorType("text", regconfig="simple"),
        Computed("to_tsvector('simple', \"text\")", persisted=True),
        index=True,
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

#     def get_url_timestamped(self, time_shift: int = 5) -> str:
#         shifted_time = self.start - time_shift
#         if shifted_time < 0:
#             shifted_time = 0
#         if self.transcription.video.channel.platform.name.lower() == "twitch":
#             hours = shifted_time // 3600
#             minutes = (shifted_time % 3600) // 60
#             seconds = shifted_time % 60
#             return f"{self.transcription.video.get_url()}?t={hours:02d}h{minutes:02d}m{seconds:02d}s"

#         elif self.transcription.video.channel.platform.name.lower() == "youtube":
#             return f"{self.transcription.video.get_url()}&t={shifted_time}"
#         raise ValueError("Could not generate url with timestamp")