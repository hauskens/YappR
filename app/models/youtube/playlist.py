from pydantic import BaseModel
from datetime import datetime


class Thumbnail(BaseModel):
    url: str
    width: int
    height: int


class LocalizedSnippet(BaseModel):
    title: str
    description: str


class Snippet(BaseModel):
    publishedAt: datetime
    channelId: str
    title: str
    description: str
    thumbnails: dict[str, Thumbnail]
    channelTitle: str
    defaultLanguage: str | None = None
    localized: LocalizedSnippet


class Status(BaseModel):
    privacyStatus: str
    podcastStatus: str  # enum value


class ContentDetails(BaseModel):
    itemCount: int


class Player(BaseModel):
    embedHtml: str


class PlaylistItem(BaseModel):
    kind: str
    etag: str
    id: str
    snippet: Snippet
    status: Status | None = None
    contentDetails: ContentDetails
    player: Player | None = None
    localizations: dict[str, LocalizedSnippet] | None = None


class PageInfo(BaseModel):
    totalResults: int
    resultsPerPage: int


class PlaylistResourceResponse(BaseModel):
    kind: str
    etag: str
    nextPageToken: str | None = None
    prevPageToken: str | None = None
    pageInfo: PageInfo | None = None
    items: list[PlaylistItem]
