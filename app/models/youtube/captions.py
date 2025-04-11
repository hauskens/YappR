from pydantic import BaseModel
from datetime import datetime


class Snippet(BaseModel):
    videoId: str
    lastUpdated: datetime
    trackKind: str
    language: str
    name: str
    audioTrackType: str
    isCC: bool
    isLarge: bool
    isEasyReader: bool
    isDraft: bool
    isAutoSynced: bool
    status: str
    failureReason: str | None = None


class Caption(BaseModel):
    kind: str
    etag: str
    id: str
    snippet: Snippet


class PageInfo(BaseModel):
    totalResults: int
    resultsPerPage: int


class CaptionResourceResponse(BaseModel):
    kind: str
    etag: str
    items: list[Caption]
