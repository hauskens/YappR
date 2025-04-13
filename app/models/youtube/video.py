from pydantic import BaseModel
from datetime import datetime, timedelta


class Thumbnail(BaseModel):
    url: str
    width: int
    height: int


class ChannelDetails(BaseModel):
    id: str
    name: str
    url: str


class Tag(BaseModel):
    value: str


class CategoryRestricts(BaseModel):
    values: list[str]


class ThumbnailDetails(BaseModel):
    actualImage: Thumbnail | None = None
    defaultImage: Thumbnail | None = None


class ContentDetails(BaseModel):
    duration: timedelta
    definition: str
    caption: bool
    licensedContentId: str | None = None


class StatusDetails(BaseModel):
    uploadStatus: str
    failureReason: str
    rejectionReason: str
    privacyStatus: str
    publishAt: datetime
    license: str
    embeddable: bool
    publicStatsViewable: bool
    madeForKids: bool
    selfDeclaredMadeForKids: bool
    containsSyntheticMedia: bool


class Statistics(BaseModel):
    viewCount: str
    likeCount: str
    dislikeCount: str
    favoriteCount: str
    commentCount: str


class PaidProductPlacementDetails(BaseModel):
    hasPaidProductPlacement: bool


class PlayerDetails(BaseModel):
    embedHtml: str
    embedHeight: int
    embedWidth: int


class TopicDetails(BaseModel):
    topicIds: list[str]
    relevantTopicIds: list[str]
    topicCategories: list[str]


class Snippet(BaseModel):
    publishedAt: datetime
    channelId: str
    title: str
    description: str
    thumbnails: dict[str, Thumbnail]
    channelTitle: str
    liveBroadcastContent: str


class RecordingDetails(BaseModel):
    recordingDate: datetime


class AudioStreamDetails(BaseModel):
    channelCount: int
    codec: str
    bitrateBps: int
    vendor: str


class VideoStreamDetails(BaseModel):
    widthPixels: int
    heightPixels: int
    frameRateFps: float
    aspectRatio: float
    codec: str
    bitrateBps: int
    rotation: str
    vendor: str


class FileDetails(BaseModel):
    fileName: str
    fileSize: int
    fileType: str
    container: str
    videoStreams: list[VideoStreamDetails]
    audioStreams: list[AudioStreamDetails]


class Stream(BaseModel):
    widthPixels: int
    heightPixels: int
    frameRateFps: float
    aspectRatio: float
    codec: str
    bitrateBps: int
    rotation: str
    vendor: str


class ProcessingDetails(BaseModel):
    processingStatus: str
    processingProgress: dict[str, int]
    processingFailureReason: str | None = None
    fileDetailsAvailability: str
    processingIssuesAvailability: str
    tagSuggestionsAvailability: str
    editorSuggestionsAvailability: str
    thumbnailsAvailability: str


class Suggestions(BaseModel):
    processingErrors: list[str]
    processingWarnings: list[str]
    processingHints: list[str]
    tagSuggestions: list[dict[str, str]]
    editorSuggestions: list[str]


class LocalizationsDetails(BaseModel):
    value: dict[str, str]


class LiveStreamingDetails(BaseModel):
    actualStartTime: datetime
    actualEndTime: datetime
    scheduledStartTime: datetime
    scheduledEndTime: datetime
    concurrentViewers: int
    activeLiveChatId: str


class VideoDetails(BaseModel):
    kind: str
    etag: str
    id: str
    snippet: Snippet
    statistics: Statistics | None = None
    status: StatusDetails | None = None
    contentDetails: ContentDetails
    paidProductPlacementDetails: PaidProductPlacementDetails | None = None
    player: PlayerDetails | None = None
    topicDetails: TopicDetails | None = None
    recordingDetails: RecordingDetails | None = None
    fileDetails: FileDetails | None = None
    processingDetails: ProcessingDetails | None = None
    suggestions: Suggestions | None = None
    liveStreamingDetails: LiveStreamingDetails | None = None
    localizations: dict[str, LocalizationsDetails] | None = None


class PageInfo(BaseModel):
    totalResults: int
    resultsPerPage: int


class VideoResourceResponse(BaseModel):
    kind: str
    etag: str
    nextPageToken: str | None = None
    prevPageToken: str | None = None
    pageInfo: PageInfo | None = None
    items: list[VideoDetails]
