from pydantic import BaseModel
from datetime import datetime


class Thumbnail(BaseModel):
    url: str
    width: int
    height: int


class Localized(BaseModel):
    title: str
    description: str


class BrandingSettingChannel(BaseModel):
    title: str
    description: str
    keywords: str
    trackingAnalyticsAccountId: str
    unsubscribedTrailer: str
    defaultLanguage: str
    country: str


class BrandingSettingWatch(BaseModel):
    textColor: str
    backgroundColor: str
    featuredPlaylistId: str


class AuditDetails(BaseModel):
    overallGoodStanding: bool
    communityGuidelinesGoodStanding: bool
    copyrightStrikesGoodStanding: bool
    contentIdClaimsGoodStanding: bool


class ContentOwnerDetails(BaseModel):
    contentOwner: str
    timeLinked: str


class TopicCategory(BaseModel):
    id: str


class TopicDetails(BaseModel):
    topicIds: list[str]
    topicCategories: list[TopicCategory]


class Status(BaseModel):
    privacyStatus: str
    isLinked: bool
    longUploadsStatus: str
    madeForKids: bool
    selfDeclaredMadeForKids: bool


class BrandingSettings(BaseModel):
    channel: BrandingSettingChannel
    watch: BrandingSettingWatch


class ContentDetails(BaseModel):
    relatedPlaylists: dict[str, str]
    topicCategories: list[TopicCategory]


class Statistics(BaseModel):
    viewCount: int
    subscriberCount: int
    hiddenSubscriberCount: int
    videoCount: int


class Snippet(BaseModel):
    title: str
    description: str
    publishedAt: datetime
    thumbnails: dict[str, Thumbnail]
    defaultLanguage: str | None = None
    localized: Localized
    country: str | None = None


class YoutubeChannel(BaseModel):
    kind: str
    etag: str
    id: str
    snippet: Snippet
    statistics: Statistics
    contentDetails: ContentDetails
    status: Status
    brandingSettings: BrandingSettings
    topicDetails: TopicDetails
    auditDetails: AuditDetails
    contentOwnerDetails: ContentOwnerDetails


class PageInfo(BaseModel):
    totalResults: int
    resultsPerPage: int


class ChannelItem(BaseModel):
    kind: str
    etag: str
    id: str
    snippet: Snippet
    statistics: Statistics | None = None


class ChannelResourceResponse(BaseModel):
    kind: str
    etag: str
    nextPageToken: str | None = None
    prevPageToken: str | None = None
    pageInfo: PageInfo | None = None
    items: list[ChannelItem]
