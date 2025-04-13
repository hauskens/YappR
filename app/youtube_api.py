import logging
from models.config import config
from googleapiclient.discovery import build

from youtube_transcript_api import YouTubeTranscriptApi, FetchedTranscript
from youtube_transcript_api.proxies import WebshareProxyConfig

from youtube_transcript_api.formatters import WebVTTFormatter

from models.youtube.channel import ChannelResourceResponse, ChannelItem
from models.youtube.playlist import PlaylistResourceResponse, PlaylistItem
from models.youtube.search import SearchResourceResponse, SearchResultItem
from models.youtube.video import VideoResourceResponse, VideoDetails
from models.youtube.captions import CaptionResourceResponse, Caption

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
    request = youtube.channels().list(part="id,snippet", forHandle=channel_tag)
    resp = request.execute()
    youtube_channels = ChannelResourceResponse.model_validate(resp)
    return youtube_channels.items.pop(0)


def get_youtube_playlist_details(channel_id: str) -> list[PlaylistItem]:
    request = youtube.playlists().list(
        part="snippet,contentDetails", channelId=channel_id, maxResults=25
    )
    resp = request.execute()
    playlists = PlaylistResourceResponse.model_validate(resp)
    return playlists.items


def get_youtube_search(channel_id: str) -> list[SearchResultItem]:
    request = youtube.search().list(
        part="snippet", type="video", channelId=channel_id, maxResults=25
    )
    resp = request.execute()
    search = SearchResourceResponse.model_validate(resp)
    return search.items


def get_videos(video_id: str) -> list[VideoDetails]:
    request = youtube.videos().list(part="snippet", id=video_id, maxResults=25)
    resp = request.execute()
    print(resp)
    videos = VideoResourceResponse.model_validate(resp)
    return videos.items


def get_captions(video_id: str) -> list[Caption]:
    request = youtube.captions().list(part="snippet", videoId=video_id)
    resp = request.execute()
    caption = CaptionResourceResponse.model_validate(resp)
    return caption.items


def fetch_transcription(video_id: str, max_retries: int = 3) -> FetchedTranscript:
    logger.info(
        f"fetch_transcription: trying to fetch transcription for video {video_id}"
    )
    max_retries = max_retries
    backoff_delay = 0.5
    attempt = 1
    while max_retries > 0:
        try:
            return ytt_api.fetch(video_id)
        except Exception as e:
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
        f"Failed to fetch transcription for video {video_id} after {max_retries} retries"
    )
