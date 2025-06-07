import requests
from .models.config import config
from googleapiclient.discovery import build
from urllib.parse import urlparse, parse_qs

from youtube_transcript_api import YouTubeTranscriptApi, FetchedTranscript
from youtube_transcript_api._errors import NoTranscriptFound
from youtube_transcript_api.proxies import WebshareProxyConfig

from .models.youtube.channel import ChannelResourceResponse, ChannelItem
from .models.youtube.playlist import PlaylistResourceResponse
from .models.youtube.search import SearchResourceResponse, SearchResultItem
from .models.youtube.video import VideoResourceResponse, VideoDetails
from .models.youtube.captions import CaptionResourceResponse
from app.logger import logger

youtube = (
    build("youtube", "v3", developerKey=config.youtube_api_key)
    if config.youtube_api_key
    else None
)

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
    if youtube is None:
        raise Exception("Youtube API key not found")
    logger.info("get_youtube_channel_details: Fetching channel details for tag: %s", channel_tag)
    request = (
        youtube.channels().list(part="id,snippet", forHandle=channel_tag).execute()
    )
    youtube_channels = ChannelResourceResponse.model_validate(request)
    try:
        return youtube_channels.items.pop(0)
    except:
        raise Exception(f"Failed to find channel on tag {channel_tag}")


def get_youtube_playlist_details(channel_id: str) -> PlaylistResourceResponse:
    if youtube is None:
        raise Exception("Youtube API key not found")
    logger.info("get_youtube_playlist_details: Fetching playlist details for channel: %s", channel_id)
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
    if youtube is None:
        raise Exception("Youtube API key not found")
    logger.info("get_videos_on_channel: Fetching videos on channel: %s", channel_id)
    if next_page_token is None:
        request = (
            youtube.search()
            .list(
                part="snippet",
                type="video",
                channelId=channel_id,
                order="date",
                maxResults=max_results,
                eventType="completed",
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
                eventType="completed",
            )
            .execute()
        )
    search = SearchResourceResponse.model_validate(request)
    return search


def get_all_videos_on_channel(channel_id: str) -> list[SearchResultItem]:
    if youtube is None:
        raise Exception("Youtube API key not found")
    logger.info("get_all_videos_on_channel: Fetching all videos on channel: %s", channel_id)
    next_page_token: str | None = None
    all_videos: list[SearchResultItem] = []
    max_requests = 50  # This is equals to 2500 videos on a channel, which is most likely never the case
    while max_requests > 0:
        max_requests -= 1
        video_result = get_videos_on_channel(channel_id, next_page_token, 50)
        all_videos.extend(video_result.items)
        logger.info(f"Found {len(video_result.items)} videos on page, next page token: {video_result.nextPageToken}, current page token: {next_page_token}")
        if video_result.nextPageToken is not None and video_result.nextPageToken != next_page_token:
            next_page_token = video_result.nextPageToken
        else:
            break
    if max_requests == 0:
        raise Exception(
            f"get_all_videos_on_channel was stopped because it found too many videos, tried {max_requests} pages with 50 videos on each page"
        )
    return all_videos


def get_videos(video_ids: list[str]) -> list[VideoDetails]:
    if youtube is None:
        raise Exception("Youtube API key not found")
    logger.info("get_videos: Fetching videos for ids: %s", ",".join(video_ids))
    all_videos: list[VideoDetails] = []
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i + 50]
        logger.debug("Fetching chunk: %s", chunk)
        request = (
            youtube.videos()
            .list(part="snippet,contentDetails", id=",".join(chunk), maxResults=50)
            .execute()
        )
        videos = VideoResourceResponse.model_validate(request)
        all_videos.extend(videos.items)

    return all_videos


def get_captions(video_id: str) -> CaptionResourceResponse:
    if youtube is None:
        raise Exception("Youtube API key not found")
    logger.info("get_captions: Fetching captions for video: %s", video_id)
    request = youtube.captions().list(part="snippet", videoId=video_id).execute()
    caption = CaptionResourceResponse.model_validate(request)
    return caption


def fetch_transcription(video_id: str) -> FetchedTranscript:
    if youtube is None:
        raise Exception("Youtube API key not found")
    logger.info("fetch_transcription: trying to fetch transcription for video %s", video_id)
    try:
        return ytt_api.fetch(video_id)
    except NoTranscriptFound:
        logger.warning(
            "Autogenerated or manual transcript not found, trying to generate one.."
        )
        transcript_list = ytt_api.list(video_id)
        transcript = transcript_list.find_transcript(["ko"])
        try:
            return transcript.translate("en").fetch()
        except Exception as e:
            logger.error("Failed to fetch transcription for video %s , exception: %s", video_id, e)
            raise ValueError("Failed to fetch transcript")


def get_youtube_thumbnail_url(url: str, quality: str = "hqdefault") -> str:
    """Extracts the YouTube video ID from a URL and returns the thumbnail URL.

    :param url: Full YouTube video URL (e.g., https://youtu.be/abc123 or https://www.youtube.com/watch?v=abc123)
    :param quality: Thumbnail quality (default: 'hqdefault')
                     Options: 'default', 'mqdefault', 'hqdefault', 'sddefault', 'maxresdefault'
    :return: Thumbnail URL or None if invalid
    """
    logger.info("get_youtube_thumbnail_url: Fetching thumbnail for url: %s", url)
    video_id = get_youtube_video_id(url)
    try:
        if not video_id:
            raise ValueError("Failed to get thumbnail because video ID was not found in url")

        return f"https://img.youtube.com/vi/{video_id}/{quality}.jpg"
    except Exception as e:
        logger.error(f"Failed to get thumbnail for url: {url}, exception: {e}")
        raise ValueError(f"Failed to get thumbnail for url: {url}, exception: {e}")

def get_youtube_video_id_from_clip(url: str) -> str | None:
    """
    Extracts the YouTube video ID from a given URL.
    """
    logger.info("get_youtube_video_id_from_clip: Fetching video ID from clip url: %s", url)
    response = requests.get(url)
    partsA = response.text.split('video_id=')
    if len(partsA) >= 2:
        # split on double quote
        partsB = partsA[1].split('"')
        if len(partsB) >= 1:
            return partsB[0]

    return None


def get_youtube_video_id(url: str) -> str:
    """
    Extracts the YouTube video ID from a given URL.

    Supported formats:
    - https://youtu.be/VIDEO_ID
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://www.youtube.com/embed/VIDEO_ID
    - https://www.youtube.com/shorts/VIDEO_ID
    - https://www.youtube.com/clip/CLIP_ID
    - With extra query params like ?t=17

    :param url: YouTube video URL
    :return: Video ID or None if not found
    """
    logger.info("get_youtube_video_id: Fetching video ID from url: %s", url)
    try:
        parsed = urlparse(url)
        hostname = parsed.netloc
        path = parsed.path
        video_id = None

        if hostname in ["youtu.be"]:
            video_id = path.lstrip("/")

        elif hostname in ["www.youtube.com", "youtube.com", "m.youtube.com"]:
            if path.startswith("/watch"):
                query = parse_qs(parsed.query)
                video_id = query.get("v", [None])[0]
            elif path.startswith("/embed/") or path.startswith("/shorts/"):
                video_id = path.split("/")[2] if len(path.split("/")) > 2 else None
            elif path.startswith("/clip/"):
                video_id = path.split("/")[2] if len(path.split("/")) > 2 else None

        if not video_id:
            raise ValueError("Could not extract video ID.")

        return video_id

    except Exception as e:
        logger.error(f"Failed to get video ID for url: {url}, exception: {e}")
        raise ValueError(f"Failed to get video ID for url: {url}, exception: {e}")
