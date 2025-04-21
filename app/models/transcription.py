from pydantic import BaseModel


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
