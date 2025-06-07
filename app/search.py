from datetime import datetime
from collections.abc import Sequence
from sqlalchemy import select
import logging
from .models.db import (
    Segments,
    Video,
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

logger = logging.getLogger("custom_logger")


def search_words_present_in_sentence(
    sentence: list[str], search_words: list[str]
) -> bool:
    return all(word in sentence for word in search_words)


def sort_function(segment: Segments | None) -> int:
    if segment is not None:
        return segment.start
    raise ValueError("Cannot sort by None")


def search_words_present_in_sentence_strict(
    sentence: list[str], search_words: list[str]
) -> bool:
    try:
        index = sentence.index(search_words[0])
        if len(search_words) == 1:
            return True
        word_index = 0
        for word in search_words[1:]:
            word_index = sentence.index(word, index)
            if word_index != index and word_index == (index + 1):
                index = word_index
        return word_index == index
    except ValueError:
        return False


def search_v2(
    search_term: str,
    channels: Sequence[Channels],
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[VideoResult]:

    # video_result: set[Video] = set()
    video_result: list[VideoResult] = []
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

    seen_segment_ids: set[int] = set()
    search_result = (
        (
            db.session.execute(
                select(Segments)
                .where(
                    Segments.text_tsv.match(search_term, postgresql_regconfig="simple"),
                    Segments.transcription_id.in_([t.id for t in transcriptions]),
                )
                .order_by(Segments.transcription_id)
                .limit(6000)
            )
        )
        .scalars()
        .all()
    )

    # Just search for the first word, based on that we will narrow down the result

    search_words = (
        loosely_sanitize_sentence(search_term.strip('"'))
        if strict_search
        else sanitize_sentence(search_term.strip('"'))
    )

    if len(search_words) == 0:
        raise ValueError("Search was too short and didnt have any useful words")

    logger.debug(f"Found matches: {len(search_result)}")
    for segment in search_result:
        # sanitize the users search query with the same function used to sanitize db
        current_sentence: list[str] = (
            loosely_sanitize_sentence(segment.text)
            if strict_search
            else sanitize_sentence(segment.text)
        )
        all_segments: list[Segments] = [segment]
        added = False
        if segment.id not in seen_segment_ids:

            # If the word is first or last part of a segment, we need to include the adjasent Segment
            try:
                word_index = current_sentence.index(search_words[0])
                if word_index == 0 and segment.previous_segment_id is not None:
                    adjasent_segment = get_segment_by_id(segment.previous_segment_id)
                    all_segments = [adjasent_segment] + all_segments
                    current_sentence = adjasent_segment.text.split() + current_sentence
                elif (
                    word_index == len(current_sentence)
                    and segment.next_segment_id is not None
                ):
                    adjasent_segment = get_segment_by_id(segment.next_segment_id)
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
                    res = SegmentsResult(
                        all_segments, segment.transcription.video, search_words
                    )
                    segment_result.append(res)
                    if video_result == []:
                        video_result.append(VideoResult([res], res.video))
                        added = True
                        seen_segment_ids.add(segment.id)
                    for v in video_result:
                        if v.video.id == res.video.id:
                            v.segment_results.append(res)
                            added = True
                            seen_segment_ids.add(segment.id)
                            continue
                    if added == False:
                        video_result.append(VideoResult([res], res.video))

            # Skip the first word as thats our baseline, search for other words in current sentence
            else:
                if search_words_present_in_sentence(current_sentence, search_words[1:]):
                    # all_segments.sort(key=sort_function)

                    res = SegmentsResult(
                        all_segments, segment.transcription.video, search_words
                    )
                    if len(video_result) == 0:
                        video_result.append(VideoResult([res], res.video))
                        added = True
                        seen_segment_ids.add(segment.id)
                    for v in video_result:
                        if v.video.id == res.video.id:
                            v.segment_results.append(res)
                            added = True
                            seen_segment_ids.add(segment.id)
                            continue
                    if added == False:
                        video_result.append(VideoResult([res], res.video))

    for v in video_result:
        v.segment_results.sort(key=lambda r: min(s.start for s in r.segments))
    video_result.sort(key=lambda v: v.video.uploaded, reverse=True)
    return video_result
