import logging
import time
from .models.config import config
from googleapiclient.discovery import build

from youtube_transcript_api import YouTubeTranscriptApi, FetchedTranscript
from youtube_transcript_api.proxies import WebshareProxyConfig

from .models.youtube.channel import ChannelResourceResponse, ChannelItem
from .models.youtube.playlist import PlaylistResourceResponse
from .models.youtube.search import SearchResourceResponse, SearchResultItem
from .models.youtube.video import VideoResourceResponse, VideoDetails
from .models.youtube.captions import CaptionResourceResponse

logger = logging.getLogger(__name__)

if config.youtube_api_key is None:
    error_message = "YOUTUBE API_KEY not configured!"
    logger.error(error_message)
    raise ValueError(error_message)

youtube = build("youtube", "v3", developerKey=config.youtube_api_key)

ytt_api = YouTubeTranscriptApi(
    proxy_config=(
        WebshareProxyConfig(
            proxy_username=config.webshare_proxy_username,
            proxy_password=config.webshare_proxy_password,
        )
        if config.webshare_proxy_password and config.webshare_proxy_username
        else None
    )
)


def get_youtube_channel_details(channel_tag: str) -> ChannelItem:
    request = (
        youtube.channels().list(part="id,snippet", forHandle=channel_tag).execute()
    )
    youtube_channels = ChannelResourceResponse.model_validate(request)
    try:
        return youtube_channels.items.pop(0)
    except:
        raise Exception(f"Failed to find channel on tag {channel_tag}")


def get_youtube_playlist_details(channel_id: str) -> PlaylistResourceResponse:
    request = (
        youtube.playlists()
        .list(part="snippet,contentDetails", channelId=channel_id, maxResults=25)
        .execute()
    )
    playlists = PlaylistResourceResponse.model_validate(request)
    return playlists


def get_videos_on_channel(
    channel_id: str, next_page_token: str | None = None, max_results: int = 5
) -> SearchResourceResponse:
    if next_page_token is None:
        request = (
            youtube.search()
            .list(
                part="snippet",
                type="video",
                channelId=channel_id,
                order="date",
                maxResults=max_results,
            )
            .execute()
        )
    else:
        request = (
            youtube.search()
            .list(
                part="snippet",
                type="video",
                channelId=channel_id,
                order="date",
                pageToken=next_page_token,
                maxResults=max_results,
            )
            .execute()
        )
    search = SearchResourceResponse.model_validate(request)
    return search


def get_all_videos_on_channel(channel_id: str) -> list[SearchResultItem]:
    next_page_token: str | None = None
    all_videos: list[SearchResultItem] = []
    max_requests = 100  # This is equals to 10000 videos on a channel, which is most likely never the case
    while max_requests > 0:
        max_requests -= 1
        video_result = get_videos_on_channel(channel_id, next_page_token, 50)
        all_videos.extend(video_result.items)
        if video_result.nextPageToken:
            next_page_token = video_result.nextPageToken
        else:
            break
    if max_requests == 0:
        raise Exception(
            f"get_all_videos_on_channel was stopped because it found too many videos, tried {max_requests} pages with 50 videos on each page"
        )
    return all_videos


def get_videos(video_ids: list[str]) -> list[VideoDetails]:
    logging.debug(f"get_videos: Fetching videos for ids: {",".join(video_ids)}")
    request = (
        youtube.videos()
        .list(part="snippet,contentDetails", id=",".join(video_ids), maxResults=25)
        .execute()
    )
    videos = VideoResourceResponse.model_validate(request)
    return videos.items


def get_captions(video_id: str) -> CaptionResourceResponse:
    request = youtube.captions().list(part="snippet", videoId=video_id).execute()
    caption = CaptionResourceResponse.model_validate(request)
    return caption


def fetch_transcription(video_id: str, max_retries: int = 1) -> FetchedTranscript:
    logger.info(
        f"fetch_transcription: trying to fetch transcription for video {video_id}"
    )
    max_retries = max_retries
    backoff_delay = 0.5
    attempt = 1
    exception = ""
    while max_retries > 0:
        try:
            return ytt_api.fetch(video_id)
        except Exception as e:
            exception = e
            logging.warning(
                f"Failed to fetch transcription for video {video_id} , (attempt {attempt}/{max_retries})"
            )
            logging.debug(
                f"Failed to fetch transcription for video {video_id} , exception: {e}"
            )
            max_retries -= 1
            attempt += 1
            time.sleep(backoff_delay * 2 ** (max_retries - 1))
    raise Exception(
        f"Failed to fetch transcription for video {video_id} after {attempt} retries with exception: {exception}"
    )
