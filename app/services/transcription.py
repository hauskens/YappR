"""
Transcription service for handling transcription-related business logic.
"""
import json
import re
import webvtt # type: ignore[import-untyped]
from collections.abc import Sequence
from io import BytesIO

from sqlalchemy import select
from app.models import db
from app.models import Transcription, Segments, TranscriptionResult, TranscriptionSource
from app.logger import logger
from app.utils import get_sec, format_duration_to_srt_timestamp


class TranscriptionService:
    """Service class for transcription-related operations."""
    
    @staticmethod
    def get_by_id(transcription_id: int) -> Transcription:
        """Get transcription by ID."""
        return db.session.execute(
            select(Transcription).filter_by(id=transcription_id)
        ).scalars().one()
    
    @staticmethod
    def get_by_video_id(video_id: int) -> Sequence[Transcription]:
        """Get all transcriptions for a video."""
        return db.session.execute(
            select(Transcription).filter_by(video_id=video_id)
        ).scalars().all()
    
    @staticmethod
    def get_segments_sorted(transcription: Transcription, descending: bool = False) -> list[Segments]:
        """Get segments for a transcription sorted by start time."""
        return sorted(transcription.segments, key=lambda v: v.start, reverse=descending)
    
    @staticmethod
    def delete_transcription(transcription_id: int) -> bool:
        """Delete a transcription and all associated data."""
        try:
            transcription = TranscriptionService.get_by_id(transcription_id)
            TranscriptionService.reset_transcription(transcription)
            db.session.query(Transcription).filter_by(id=transcription_id).delete()
            db.session.commit()
            logger.info(f"Deleted transcription {transcription_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete transcription {transcription_id}: {e}")
            db.session.rollback()
            return False
    
    @staticmethod
    def reset_transcription(transcription: Transcription):
        """Reset a transcription by deleting segments and marking as unprocessed."""
        TranscriptionService.delete_attached_segments(transcription)
        transcription.processed = False
    
    @staticmethod
    def delete_attached_segments(transcription: Transcription):
        """Delete all segments attached to a transcription."""
        db.session.query(Segments).filter_by(transcription_id=transcription.id).delete()
        transcription.processed = False
        db.session.commit()
    
    @staticmethod
    def process_transcription(transcription: Transcription, force: bool = False):
        """Process a transcription file into segments."""
        logger.info(f"Task queued, parsing transcription for {transcription.id}, - {force}")
        
        if transcription.processed and not force and len(transcription.segments) == 0:
            logger.info(f"Transcription {transcription.id}, already processed.. skipping")
            return
            
        if force:
            TranscriptionService.reset_transcription(transcription)
            
        if transcription.file_extention == "vtt":
            TranscriptionService.parse_vtt(transcription)
        elif transcription.file_extention == "json":
            TranscriptionService.parse_json(transcription)
            
        transcription.processed = True
        db.session.commit()
    
    @staticmethod
    def to_srt(transcription: Transcription) -> str:
        """Convert the transcription to SRT format.

        Returns:
            str: The transcription in SRT format
        """
        if not transcription.processed:
            TranscriptionService.process_transcription(transcription)

        srt_content = TranscriptionService.convert_to_srt(transcription)
        return srt_content
    
    @staticmethod
    def to_json(transcription: Transcription) -> str:
        """Convert the transcription to JSON format.

        Returns:
            str: The transcription in JSON format
        """
        if not transcription.processed:
            TranscriptionService.process_transcription(transcription)

        segments = TranscriptionService.get_segments_sorted(transcription)
        json_segments = []

        for segment in segments:
            json_segments.append({
                "text": segment.text,
                "start": segment.start,
                "end": segment.end
            })

        result = {
            "segments": json_segments,
            "language": transcription.language
        }

        return json.dumps(result, ensure_ascii=False)
    
    @staticmethod
    def save_as_srt(transcription: Transcription, output_path: str | None = None) -> str:
        """Convert the transcription to SRT format and save it to a file.

        Args:
            transcription: The transcription to convert
            output_path: Path to save the SRT file. If None, a path will be generated
                        based on the video ID and transcription ID.

        Returns:
            str: Path to the saved SRT file
        """
        srt_content = TranscriptionService.to_srt(transcription)

        if output_path is None:
            # Generate a filename based on video ID and transcription ID
            output_path = f"transcription_{transcription.video_id}_{transcription.id}.srt"

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

        logger.info(f"Saved SRT file to {output_path}")
        return output_path
    
    @staticmethod
    def save_as_json(transcription: Transcription, output_path: str | None = None) -> str:
        """Convert the transcription to JSON format and save it to a file.

        Args:
            transcription: The transcription to convert
            output_path: Path to save the JSON file. If None, a path will be generated
                        based on the video ID and transcription ID.

        Returns:
            str: Path to the saved JSON file
        """
        json_content = TranscriptionService.to_json(transcription)

        if output_path is None:
            # Generate a filename based on video ID and transcription ID
            output_path = f"transcription_{transcription.video_id}_{transcription.id}.json"

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json_content)

        logger.info(f"Saved JSON file to {output_path}")
        return output_path
    
    @staticmethod
    def parse_json(transcription: Transcription):
        """Parse a JSON transcription file into segments."""
        logger.info(f"Processing json transcription: {transcription.id}")
        segments: list[Segments] = []
        content = TranscriptionResult.model_validate_json(
            transcription.file.file.read().decode()
        )
        TranscriptionService.reset_transcription(transcription)

        previous_segment: Segments | None = None
        logger.info(f"Processing json transcription: {transcription.id}")
        
        for caption in content.segments:
            start = int(caption.start)
            if caption.text == "":
                continue
            if previous_segment is not None and caption.text == previous_segment.text:
                continue

            segment = Segments(
                text=caption.text,
                start=start,
                transcription_id=transcription.id,
                end=int(caption.end),
                previous_segment_id=(
                    previous_segment.id if previous_segment is not None else None
                ),
            )
            db.session.add(segment)
            db.session.flush()
            
            if previous_segment is not None:
                previous_segment.next_segment_id = segment.id
                db.session.add(previous_segment)
                db.session.flush()

            previous_segment = segment
            segments.append(segment)
            
        db.session.commit()
        logger.info(f"Done processing transcription: {transcription.id}")
    
    @staticmethod
    def parse_vtt(transcription: Transcription):
        """Parse a VTT transcription file into segments."""
        logger.info(f"Processing vtt transcription: {transcription.id}")
        segments: list[Segments] = []
        content = BytesIO(transcription.file.file.read())
        previous_segment: Segments | None = None
        
        for caption in webvtt.from_buffer(content):
            start = get_sec(caption.start)
            # remove annotations, such as [music]
            text = re.sub(r"\[.*?\]", "", caption.text).strip().lower()

            if "\n" in text:
                continue
            if text == "":
                continue
            if previous_segment is not None and text == previous_segment.text:
                continue

            segment = Segments(
                text=text,
                start=start,
                transcription_id=transcription.id,
                end=get_sec(caption.end),
                previous_segment_id=(
                    previous_segment.id if previous_segment is not None else None
                ),
            )
            db.session.add(segment)
            db.session.flush()
            
            if previous_segment is not None:
                previous_segment.next_segment_id = segment.id
                db.session.add(previous_segment)
                db.session.flush()

            previous_segment = segment
            segments.append(segment)
            
        db.session.commit()
        logger.info(f"Done processing transcription: {transcription.id}")
    
    @staticmethod
    def create(video_id: int, language: str, file_extension: str, file_content, 
               source: TranscriptionSource = TranscriptionSource.Unknown) -> Transcription:
        """Create a new transcription."""
        transcription = Transcription(
            video_id=video_id,
            language=language,
            file_extention=file_extension,
            file=file_content,
            source=source
        )
        db.session.add(transcription)
        db.session.commit()
        logger.info(f"Created transcription for video {video_id}")
        return transcription
    
    @staticmethod
    def update(transcription_id: int, **kwargs) -> Transcription:
        """Update transcription fields."""
        transcription = TranscriptionService.get_by_id(transcription_id)
        for key, value in kwargs.items():
            if hasattr(transcription, key):
                setattr(transcription, key, value)
        db.session.commit()
        return transcription
    
    @staticmethod
    
    def convert_to_srt(transcription: Transcription | dict) -> str:
        """Convert transcription data to SRT format.
        Only one of transcription or segments should be provided.

        Args:
            transcription: The transcription to convert
            segments: The segments to convert

        Returns:
            str: The transcription in SRT format
        """
        # Convert to SRT format
        srt_content = []

        if isinstance(transcription, Transcription):
            segments = TranscriptionService.get_segments_sorted(transcription)
        elif isinstance(transcription, dict) and 'segments' in transcription:
            segments = transcription.get('segments', [])
        else:
            raise ValueError("Invalid transcription format")

        for i, segment in enumerate(segments, 1):
            # Handle both dict access and object attribute access
            if isinstance(segment, dict):
                start = segment.get('start', 0)
                end = segment.get('end', 0)
                text = segment.get('text', '')
            else:
                # Assume object with attributes
                start = getattr(segment, 'start', 0)
                end = getattr(segment, 'end', 0)
                text = getattr(segment, 'text', '')

            # Format timestamps as HH:MM:SS,mmm
            start_time = format_duration_to_srt_timestamp(start)
            end_time = format_duration_to_srt_timestamp(end)

            # Add entry to SRT content
            srt_content.append(f"{i}\n{start_time} --> {end_time}\n{text}\n")

        srt_text = "\n".join(srt_content)
        return srt_text


class SegmentService:
    """Service class for segment-related operations."""
    
    @staticmethod
    def get_by_id(segment_id: int) -> Segments:
        """Get segment by ID."""
        return db.session.query(Segments).filter_by(id=segment_id).one()
    
    @staticmethod
    def get_url_timestamped(segment: Segments, time_shift: int = 5) -> str:
        """Get URL with timestamp for a segment."""
        # Import here to avoid circular imports
        from .video import VideoService
        
        shifted_time = segment.start - time_shift
        if shifted_time < 0:
            shifted_time = 0
            
        return VideoService.get_url_with_timestamp(segment.transcription.video, shifted_time)


# For template accessibility, create simple function interfaces
def get_transcription_service() -> TranscriptionService:
    """Get transcription service instance for use in templates."""
    return TranscriptionService()


def get_segment_service() -> SegmentService:
    """Get segment service instance for use in templates."""
    return SegmentService()


def transcription_to_srt(transcription: Transcription) -> str:
    """Convert transcription to SRT for use in templates."""
    return TranscriptionService.to_srt(transcription)


def transcription_to_json(transcription: Transcription) -> str:
    """Convert transcription to JSON for use in templates."""
    return TranscriptionService.to_json(transcription)


def segment_get_url_timestamped(segment: Segments, time_shift: int = 5) -> str:
    """Get segment URL with timestamp for use in templates."""
    return SegmentService.get_url_timestamped(segment, time_shift)