from dataclasses import dataclass
from .transcription import Segments
from .video import Video


@dataclass
class SegmentsResult:
    segments: list[Segments]
    video: Video
    search_words: list[str]

    def get_sentences(self) -> str:
        full_sentence: str = ""
        for segment in self.segments:
            full_sentence += " " + segment.text
        return full_sentence

    def get_sentences_formated(self) -> str:
        full_sentence = self.get_sentences()
        for word in self.search_words:
            full_sentence = full_sentence.replace(word, word.upper())
        return full_sentence

    def start_time(self) -> int:
        min_segment = min(self.segments, key=lambda x: x.start)
        return min_segment.start

    def end_time(self) -> int:
        max_segment = max(self.segments, key=lambda x: x.end)
        return max_segment.end

    def get_url(self) -> str:
        min_segment = min(self.segments, key=lambda x: x.start)
        from app.services.transcription import SegmentService
        return SegmentService.get_url_timestamped(min_segment)


@dataclass
class VideoResult:
    segment_results: list[SegmentsResult]
    video: Video
