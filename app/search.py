from datetime import datetime
from collections.abc import Sequence
import logging
from .models.db import (
    Segments,
    Video,
    Channels,
)
from .models.search import SegmentsResult
from .retrievers import (
    get_transcriptions_on_channels,
    get_transcriptions_on_channels_daterange,
    search_wordmaps_by_transcriptions,
    get_segments_by_wordmap,
    get_segment_by_id,
)
from .utils import sanitize_sentence, loosely_sanitize_sentence

logger = logging.getLogger(__name__)


def search_words_present_in_sentence(
    sentence: list[str], search_words: list[str]
) -> bool:
    return all(word in sentence for word in search_words)


def search_words_present_in_sentence_strict(
    sentence: list[str], search_words: list[str]
) -> bool:
    try:
        index = sentence.index(search_words[0])
        word_index = 0
        for word in search_words[1:]:
            word_index = sentence.index(word, index)
            if word_index != index and word_index == (index + 1):
                index = word_index
        logger.info(
            f"Looking for potential word: {sentence} = {search_words} - w{word_index} - i{index} = {word_index == index}"
        )
        return word_index == index
    except ValueError:
        return False


def search(
    search_term: str,
    channels: Sequence[Channels],
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> tuple[list[SegmentsResult], list[Video]]:

    logger.info(f"Searching for '{search_term}'")
    video_result: set[Video] = set()
    segment_result: list[SegmentsResult] = []
    transcriptions = None
    strict_search = search_term.startswith('"') and search_term.endswith('"')
    logger.info(f"strict search: {strict_search}")

    # If dates are found, limit the transcriptions based on dates
    if start_date is None and end_date is None:
        transcriptions = get_transcriptions_on_channels(channels)
    if start_date is not None and end_date is not None:
        transcriptions = get_transcriptions_on_channels_daterange(
            channels, start_date, end_date
        )
    if transcriptions is None:
        raise ValueError("No transcriptions found on channel / daterange")

    # sanitize the users search query with the same function used to sanitize db
    search_words = sanitize_sentence(search_term.strip('"'))

    # Just search for the first word, based on that we will narrow down the result
    search_result = search_wordmaps_by_transcriptions(search_words[0], transcriptions)

    for wordmap in search_result:
        segments = get_segments_by_wordmap(wordmap)
        for segment in segments:
            current_sentence: list[str] = (
                loosely_sanitize_sentence(segment.text)
                if strict_search
                else sanitize_sentence(segment.text)
            )
            all_segments: list[Segments] = [segment]

            # If the word is first or last part of a segment, we need to include the adjasent Segment
            # TODO: need to query for nearest segment, this does sometimes fail
            try:
                word_index = current_sentence.index(search_words[0])
                if word_index == 0:
                    adjasent_segment = get_segment_by_id(segment.id - 1)
                    all_segments = [adjasent_segment] + all_segments
                    current_sentence = adjasent_segment.text.split() + current_sentence
                elif word_index == len(current_sentence):
                    adjasent_segment = get_segment_by_id(segment.id + 1)
                    all_segments.append(adjasent_segment)
                    current_sentence += adjasent_segment.text.split()
            except:
                logger.debug(
                    f"Could not find adjasent segment on segment id {segment.id}"
                )
            if strict_search:
                if search_words_present_in_sentence_strict(
                    current_sentence, search_words
                ):
                    segment_result.append(
                        SegmentsResult(
                            all_segments, wordmap.transcription.video, search_words
                        )
                    )
                    video_result.add(wordmap.transcription.video)

            # Skip the first word as thats our baseline, search for other words in current sentence
            elif strict_search is False:
                if search_words_present_in_sentence(current_sentence, search_words[1:]):
                    segment_result.append(
                        SegmentsResult(
                            all_segments, wordmap.transcription.video, search_words
                        )
                    )
                    video_result.add(wordmap.transcription.video)

    logger.info(
        f"Search found {len(video_result)} videos with {len(segment_result)} segments"
    )
    return segment_result, sorted(video_result, key=lambda x: x.uploaded, reverse=True)
