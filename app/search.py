from datetime import datetime
from collections.abc import Sequence
from sqlalchemy import select
from app.logger import logger
from .models import db
from .models.channel import Channels
from .models.transcription import Segments
from .models.search import SegmentsResult, VideoResult
from .services import TranscriptionService
from .utils import sanitize_sentence
import time



def search_v2(
    search_term: str,
    channels: Sequence[Channels],
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[VideoResult]:
    """
    Search for videos containing the given search term using PostgreSQL text search.
    """
    timer = time.perf_counter()
    video_result: list[VideoResult] = []
    video_lookup: dict[int, VideoResult] = {}
    
    # Get transcriptions
    if start_date is None and end_date is None:
        transcriptions = TranscriptionService.get_transcriptions_on_channels(channels)
    elif start_date is not None and end_date is not None:
        transcriptions = TranscriptionService.get_transcriptions_on_channels_daterange(
            channels, start_date, end_date
        )
    else:
        transcriptions = None
        
    if transcriptions is None:
        raise ValueError("No transcriptions found on channel / daterange")

    # Handle quoted search terms for phrase matching
    db_search_term = search_term
    if search_term.startswith('"') and search_term.endswith('"'):
        # For phrase search, PostgreSQL handles this natively
        db_search_term = search_term
    
    # Single database query with text search
    search_result = db.session.execute(
        select(Segments)
        .where(
            Segments.text_tsv.match(db_search_term, postgresql_regconfig="simple"),
            Segments.transcription_id.in_([t.id for t in transcriptions]),
        )
        .order_by(Segments.transcription_id, Segments.start)
        .limit(6000)
    ).scalars().all()

    # Process results - trust the database's text search
    search_words = sanitize_sentence(search_term.strip('"'))
    processed_segments = set()  # Track processed segments to avoid duplicates
    
    for segment in search_result:
        source_video = segment.transcription.video
        
        # Create unique identifier for this segment
        segment_key = (segment.id, segment.transcription_id, segment.start, segment.end)
        
        if segment_key in processed_segments:
            continue  # Skip already processed segments
        
        processed_segments.add(segment_key)
        
        # Check if this source video has linked target videos
        target_video = source_video
        translated_segment = segment
        
        if source_video.source_mappings:
            # This is a source video with target mappings - use the target video instead
            # Get the first active mapping (primary target)
            active_mapping = next((mapping for mapping in source_video.source_mappings if mapping.active), None)
            
            if active_mapping:
                target_video = active_mapping.target_video
                
                # Translate the segment timestamps from source to target
                translated_start = active_mapping.translate_source_to_target(segment.start)
                translated_end = active_mapping.translate_source_to_target(segment.end)
                
                # Only use the target video if we can successfully translate the timestamps
                if translated_start is not None and translated_end is not None:
                    # Create a copy of the segment with translated timestamps
                    # We'll store the original segment but override timestamps in SegmentsResult
                    translated_segment = segment  # Keep original segment for text content
                    translated_segment._translated_start = translated_start
                    translated_segment._translated_end = translated_end
                    translated_segment._is_translated = True
                else:
                    # If translation fails, fall back to source video
                    target_video = source_video
                    translated_segment = segment
        
        segment_result = SegmentsResult([translated_segment], target_video, search_words)
        
        video_id = target_video.id
        if video_id in video_lookup:
            # Check if we already have a segment result for this same timestamp to avoid duplicates
            existing_timestamps = {r.start_time() for r in video_lookup[video_id].segment_results}
            segment_start = segment_result.start_time()
            
            # Only add if we don't already have a segment at this exact timestamp
            if segment_start not in existing_timestamps:
                video_lookup[video_id].segment_results.append(segment_result)
        else:
            new_video_result = VideoResult([segment_result], target_video)
            video_result.append(new_video_result)
            video_lookup[video_id] = new_video_result

    # Sort results
    for v in video_result:
        v.segment_results.sort(key=lambda r: r.start_time())
    video_result.sort(key=lambda v: v.video.uploaded, reverse=True)

    end_time = time.perf_counter()
    execution_time = end_time - timer
    logger.info(f"search executed in {execution_time*1000:.2f}ms", extra={
        "channels": [c.name for c in channels], 
        "duration": execution_time*1000, 
        "result_count": len(video_result)
    })
    return video_result


