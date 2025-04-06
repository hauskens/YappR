from dataclasses import dataclass


@dataclass
class Thumbnail:
    url: str
    height: int
    width: int


@dataclass
class VideoData:
    _type: str
    ie_key: str
    id: str
    url: str
    title: str
    description: str
    duration: float
    channel_id: str | None
    channel: str | None
    channel_url: str | None
    uploader: str | None
    uploader_id: str | None
    uploader_url: str | None
    thumbnails: list[Thumbnail] | None
    timestamp: str
    release_timestamp: str | None
    availability: str | None
    view_count: int
    live_status: str | None
    channel_is_verified: bool | None


@dataclass
class SubtitleData:
    video_id: str
    path: str
    language: str
    extention: str
