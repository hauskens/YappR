from pydantic import BaseModel
from datetime import datetime


class Thumbnail(BaseModel):
    url: str
    width: int
    height: int


class Id(BaseModel):
    kind: str
    videoId: str | None = None
    channelId: str | None = None  # make channelId optional
    playlistId: str | None = None  # make playlistId optional


class Snippet(BaseModel):
    publishedAt: datetime
    channelId: str
    title: str
    description: str
    thumbnails: dict[str, Thumbnail]
    channelTitle: str
    liveBroadcastContent: str


class SearchResultItem(BaseModel):
    kind: str
    etag: str
    id: Id
    snippet: Snippet


class PageInfo(BaseModel):
    totalResults: int
    resultsPerPage: int


class SearchResourceResponse(BaseModel):
    kind: str
    etag: str
    nextPageToken: str | None = None
    prevPageToken: str | None = None
    pageInfo: PageInfo | None = None
    items: list[SearchResultItem]
