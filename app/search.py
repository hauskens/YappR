from datetime import datetime
from collections.abc import Sequence
from sqlalchemy import select
from app.logger import logger
from .models.db import (
    Segments,
    Channels,
    db,
)
from .models.search import SegmentsResult, VideoResult
from .retrievers import (
    get_transcriptions_on_channels,
    get_transcriptions_on_channels_daterange,
    get_segment_by_id,
)
from .utils import sanitize_sentence, loosely_sanitize_sentence
import time


def search_words_present_in_sentence(
    sentence: list[str], search_words: list[str]
) -> bool:
    sentence_set = set(sentence)
    return all(word in sentence_set for word in search_words)


def _add_segment_to_results(
    segment_result: "SegmentsResult",
    video_results: list["VideoResult"],
    video_lookup: dict[int, "VideoResult"],
    seen_segment_ids: set[int],
    segment_id: int,
) -> None:
    """Helper function to add a segment result to the appropriate video result"""
    video_id = segment_result.video.id

    if video_id in video_lookup:
        # Add to existing video
        video_lookup[video_id].segment_results.append(segment_result)
    else:
        # Create new video result
        new_video_result = VideoResult([segment_result], segment_result.video)
        video_results.append(new_video_result)
        video_lookup[video_id] = new_video_result

    seen_segment_ids.add(segment_id)


def search_v2(
    search_term: str,
    channels: Sequence[Channels],
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[VideoResult]:
    """
    Properly optimized version of search_v2 with fast Python operations
    """
    timer = time.perf_counter()
    video_result: list[VideoResult] = []
    video_lookup: dict[int, VideoResult] = {}  # For O(1) video lookups
    transcriptions = None
    strict_search = search_term.startswith('"') and search_term.endswith('"')
    logger.info("strict search status: %s", strict_search)

    # Get transcriptions (same as original)
    if start_date is None and end_date is None:
        transcriptions = get_transcriptions_on_channels(channels)
    if start_date is not None and end_date is not None:
        transcriptions = get_transcriptions_on_channels_daterange(
            channels, start_date, end_date
        )
    if transcriptions is None:
        raise ValueError("No transcriptions found on channel / daterange")

    seen_segment_ids: set[int] = set()
    search_result = (
        (
            db.session.execute(
                select(Segments)
                .where(
                    Segments.text_tsv.match(
                        search_term, postgresql_regconfig="simple"),
                    Segments.transcription_id.in_(
                        [t.id for t in transcriptions]),
                )
                .order_by(Segments.transcription_id)
                .limit(6000)
            )
        )
        .scalars()
        .all()
    )

    search_words = (
        loosely_sanitize_sentence(search_term.strip('"'))
        if strict_search
        else sanitize_sentence(search_term.strip('"'))
    )

    if len(search_words) == 0:
        raise ValueError(
            "Search was too short and didnt have any useful words")

    for segment in search_result:
        # Sanitize the segment text using same function as original
        current_sentence: list[str] = (
            loosely_sanitize_sentence(segment.text)
            if strict_search
            else sanitize_sentence(segment.text)
        )
        all_segments: list[Segments] = [segment]

        if segment.id not in seen_segment_ids:
            # Implement adjacent segment logic (missing from previous optimized version)
            try:
                word_index = current_sentence.index(search_words[0])
                if word_index == 0 and segment.previous_segment_id is not None:
                    adjacent_segment = get_segment_by_id(
                        segment.previous_segment_id)
                    all_segments = [adjacent_segment] + all_segments
                    # Use same sanitization as main segment for consistency
                    adjacent_sentence = (
                        loosely_sanitize_sentence(adjacent_segment.text)
                        if strict_search
                        else sanitize_sentence(adjacent_segment.text)
                    )
                    current_sentence = adjacent_sentence + current_sentence
                elif (
                    word_index == len(current_sentence) - 1
                    and segment.next_segment_id is not None
                ):
                    adjacent_segment = get_segment_by_id(
                        segment.next_segment_id)
                    all_segments.append(adjacent_segment)
                    # Use same sanitization as main segment for consistency
                    adjacent_sentence = (
                        loosely_sanitize_sentence(adjacent_segment.text)
                        if strict_search
                        else sanitize_sentence(adjacent_segment.text)
                    )
                    current_sentence += adjacent_sentence
            except (ValueError, AttributeError):
                pass
            # Check if segment matches search criteria
            matches = (
                search_words_present_in_sentence_strict(
                    current_sentence, search_words)
                if strict_search
                else search_words_present_in_sentence(current_sentence, search_words[1:])
            )

            if matches:
                res = SegmentsResult(
                    all_segments, segment.transcription.video, search_words)
                _add_segment_to_results(
                    res, video_result, video_lookup, seen_segment_ids, segment.id)

    for v in video_result:
        v.segment_results.sort(key=lambda r: min(s.start for s in r.segments))
    video_result.sort(key=lambda v: v.video.uploaded, reverse=True)

    end_time = time.perf_counter()
    execution_time = end_time - timer
    logger.info(f"search_v2 executed in {execution_time*1000:.2f}ms")
    return video_result


def search_words_present_in_sentence_strict(
    sentence: list[str], search_words: list[str]
) -> bool:
    """looks for consecutive words"""
    if not search_words:
        return False

    sentence_len = len(sentence)
    search_len = len(search_words)

    if search_len > sentence_len:
        return False

    # Use sliding window to check for consecutive matches
    for i in range(sentence_len - search_len + 1):
        if sentence[i:i + search_len] == search_words:
            return True
    return False
