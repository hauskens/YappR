from dataclasses import dataclass
from .db import Segments, Video


@dataclass
class SegmentsResult:
    segments: list[Segments]
    video: Video

    def get_sentences(self) -> str:
        full_sentence: str = ""
        for segment in self.segments:
            full_sentence += " " + segment.text
        return full_sentence

    def start_time(self) -> int:
        return min(self.segments, key=lambda x: x.start).start

    def end_time(self) -> int:
        return max(self.segments, key=lambda x: x.end).end
