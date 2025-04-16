from datetime import datetime
import logging
from .models.db import (
    Segments,
    Video,
)
from .models.search import SegmentsResult
from .retrievers import (
    get_broadcaster,
    get_broadcaster_channels,
    get_transcriptions_on_channels,
    get_transcriptions_on_channels_daterange,
    search_wordmaps_by_transcription,
    get_segments_by_wordmap,
    get_segment_by_id,
)
from .utils import sanitize_sentence, sw


logger = logging.getLogger(__name__)


def search_words_present_in_sentence(sentence: list[str], search_words: list[str]):
    return all(word in sentence for word in search_words)


def sanitize_search_query(search: list[str]) -> list[str]:
    return [word for word in search if word not in sw]


def search(
    search_term: str, broadcaster_id: int
) -> tuple[list[SegmentsResult], set[Video]]:
    broadcaster = get_broadcaster(int(broadcaster_id))
    if broadcaster is None:
        raise ValueError("Broadcaster not found")
    logger.info(f"Searching for '{search_term}' on {broadcaster.name}")
    channels = get_broadcaster_channels(int(broadcaster_id))
    video_result: set[Video] = set()
    segment_result: list[SegmentsResult] = []
    if channels is None:
        raise ValueError(f"No channels found on Broadcaster '{broadcaster.name}")
    transcriptions = get_transcriptions_on_channels(channels)
    search_words = sanitize_sentence(search_term)
    logger.info(f"Searching for '{search_words}' on {broadcaster.name}")
    for t in transcriptions:
        search_result = search_wordmaps_by_transcription(search_words[0], t)
        for wordmap in search_result:
            segments = get_segments_by_wordmap(wordmap)
            for segment in segments:
                current_sentence: list[str] = sanitize_sentence(segment.text)
                all_segments: list[Segments] = [segment]
                # If the word is first or last part of a segment, we need to include the adjasent Segment
                word_index = current_sentence.index(search_words[0])
                if word_index == 0:
                    adjasent_segment = get_segment_by_id(segment.id - 1)
                    all_segments = [adjasent_segment] + all_segments
                    current_sentence = adjasent_segment.text.split() + current_sentence
                elif word_index == len(current_sentence):
                    adjasent_segment = get_segment_by_id(segment.id + 1)
                    all_segments.append(adjasent_segment)
                    current_sentence += adjasent_segment.text.split()
                # Skip the first word as thats our baseline, search for other words in current sentence
                if search_words_present_in_sentence(current_sentence, search_words[1:]):
                    segment_result.append(
                        SegmentsResult(all_segments, t.video, search_words)
                    )
                    video_result.add(t.video)

    logger.info(
        f"Search found {len(video_result)} videos with {len(segment_result)} segments"
    )
    return segment_result, sorted(video_result, key=lambda x: x.uploaded, reverse=True)


def search_date(
    search_term: str, broadcaster_id: int, start_date: datetime, end_date: datetime
) -> tuple[list[SegmentsResult], set[Video]]:
    broadcaster = get_broadcaster(int(broadcaster_id))
    if broadcaster is None:
        raise ValueError("Broadcaster not found")
    logger.info(f"Searching for '{search_term}' on {broadcaster.name}")
    channels = get_broadcaster_channels(int(broadcaster_id))
    video_result: set[Video] = set()
    segment_result: list[SegmentsResult] = []
    if channels is None:
        raise ValueError(f"No channels found on Broadcaster '{broadcaster.name}")
    transcriptions = get_transcriptions_on_channels_daterange(
        channels, start_date, end_date
    )
    search_words = sanitize_sentence(search_term)
    logger.info(f"Searching for '{search_words}' on {broadcaster.name}")
    for t in transcriptions:
        search_result = search_wordmaps_by_transcription(search_words[0], t)
        for wordmap in search_result:
            segments = get_segments_by_wordmap(wordmap)
            for segment in segments:
                current_sentence: list[str] = sanitize_sentence(segment.text)
                all_segments: list[Segments] = [segment]
                # If the word is first or last part of a segment, we need to include the adjasent Segment
                word_index = current_sentence.index(search_words[0])
                if word_index == 0:
                    adjasent_segment = get_segment_by_id(segment.id - 1)
                    all_segments = [adjasent_segment] + all_segments
                    current_sentence = adjasent_segment.text.split() + current_sentence
                elif word_index == len(current_sentence):
                    adjasent_segment = get_segment_by_id(segment.id + 1)
                    all_segments.append(adjasent_segment)
                    current_sentence += adjasent_segment.text.split()
                # Skip the first word as thats our baseline, search for other words in current sentence
                if search_words_present_in_sentence(current_sentence, search_words[1:]):
                    segment_result.append(
                        SegmentsResult(all_segments, t.video, search_words)
                    )
                    video_result.add(t.video)

    logger.info(
        f"Search found {len(video_result)} videos with {len(segment_result)} segments"
    )
    return segment_result, sorted(video_result, key=lambda x: x.uploaded, reverse=True)
