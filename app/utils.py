# originally inspired by https://github.com/lawrencehook/SqueexVodSearch/blob/main/preprocessing/scripts/parse.py

import re
import os
import requests
from datetime import datetime, timedelta
from app.models.youtube.video import VideoDetails
from app.models.config import config
from twitchAPI.twitch import Video
from app.logger import logger
from urllib.parse import urlparse, parse_qs

if os.getenv("NLTK_ENABLED", "true") == "true":
    import nltk # type: ignore
    from nltk.corpus import stopwords # type: ignore
    from nltk.tag import pos_tag # type: ignore
    from nltk.tokenize import word_tokenize # type: ignore
    from nltk.stem import PorterStemmer # type: ignore
    _ = nltk.download("stopwords")
    _ = nltk.download("averaged_perceptron_tagger_eng")
    _ = nltk.download("punkt_tab")

    sw = stopwords.words("english")
    ps = PorterStemmer()


# This function is used by both parsing and searching to ensure we are getting good search results.
def sanitize_sentence(sentence: str) -> list[str]:
    words = pos_tag(word_tokenize(sentence))
    result: list[str] = []
    for word in words:
        if word[0] not in sw:
            word = ps.stem(word[0])
            result.append(word)
    return result


def seconds_to_string(seconds: int | float) -> str:
    return str(timedelta(seconds=int(seconds)))


def loosely_sanitize_sentence(sentence: str) -> list[str]:
    result: list[str] = []
    words = word_tokenize(sentence)
    for word in words:
        if word not in sw:
            result.append(word)
    return result


def get_sec(time_str: str) -> int:
    """Get seconds from time string in formats:
    - HH:MM:SS
    - XhYmZs (e.g. 1h30m, 45m30s, 30s)
    """
    # First try HH:MM:SS format
    if ":" in time_str:
        h, m, s = re.sub(r"\..*$", "", time_str).split(":")
        return int(h) * 3600 + int(m) * 60 + int(s)
    
    # Handle XhYmZs format
    total_seconds = 0
    
    # Find hours
    hour_match = re.search(r'(\d+)h', time_str)
    if hour_match:
        total_seconds += int(hour_match.group(1)) * 3600
    
    # Find minutes
    minute_match = re.search(r'(\d+)m', time_str)
    if minute_match:
        total_seconds += int(minute_match.group(1)) * 60
    
    # Find seconds
    second_match = re.search(r'(\d+)s', time_str)
    if second_match:
        total_seconds += int(second_match.group(1))
    
    return total_seconds


def save_yt_thumbnail(video: VideoDetails, force: bool = False) -> str:
    path = config.cache_location + video.id
    thumbnail = video.snippet.thumbnails.get("high")
    if thumbnail is None:
        thumbnail = video.snippet.thumbnails.get("default")
    if thumbnail is None:
        logger.error("No thumbnail available for video %s", video.id)
        raise ValueError(f"No thumbnail available for video {video.id}")
    if hasattr(thumbnail, "url"):
        logger.info("Fetching thumbnail, %s", thumbnail.url)
        if not os.path.exists(path):
            response = requests.get(thumbnail.url)
            if response.status_code == 200:
                with open(path, "wb") as f:
                    _ = f.write(response.content)
                return path
        return path
    raise (ValueError(f"Failed to download thumbnail for video {video.id}"))


def save_twitch_thumbnail(video: Video, force: bool = False) -> str:
    path = config.cache_location + video.id
    thumbnail = video.thumbnail_url
    thumbnail_url = thumbnail.replace("%{width}", str(320)).replace(
        "%{height}", str(180)
    )
    logger.debug("Fetching thumbnail, %s", thumbnail_url)
    if not os.path.exists(path) or force:
        response = requests.get(thumbnail_url)
        if response.status_code == 200:
            with open(path, "wb") as f:
                _ = f.write(response.content)
            return path
    return path


def get_valid_date(date_string: str) -> datetime | None:
    try:
        date = datetime.strptime(date_string, "%Y-%m-%d")
        return date
    except ValueError:
        logger.warning("didnt match date on %s", date_string)
        return None

def get_youtube_url_with_timestamp(url: str, seconds_offset: float) -> str:
    """Generate a URL to the video at a specific timestamp.
    
    Args:
        seconds_offset: Number of seconds from the start of the video
        
    Returns:
        URL string with appropriate timestamp format for the platform
    """
    
    if seconds_offset <= 0:
        raise ValueError("Seconds offset must be positive")
    
    # YouTube uses t=123s format (seconds)
    return f"{url}&t={int(seconds_offset)}"
    
def get_twitch_url_with_timestamp(url: str, seconds_offset: float) -> str:
    """Generate a URL to the video at a specific timestamp.
    
    Args:
        seconds_offset: Number of seconds from the start of the video
        
    Returns:
        URL string with appropriate timestamp format for the platform
    """
    
    if seconds_offset <= 0:
        raise ValueError("Seconds offset must be positive")
    
    # Twitch uses t=01h23m45s format
    hours = int(seconds_offset // 3600)
    minutes = int((seconds_offset % 3600) // 60)
    seconds = int(seconds_offset % 60)
        
    if hours > 0:
        timestamp = f"{hours:02d}h{minutes:02d}m{seconds:02d}s"
    else:
        timestamp = f"{minutes:02d}m{seconds:02d}s"
            
    return f"{url}?t={timestamp}"


def get_timestamp_from_youtube_url(url: str) -> int | None:
    """Get the timestamp from a YouTube URL"""
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    if 't' in query_params:
        return int(query_params['t'][0])
    return None
    
def get_timestamp_from_twitch_url(url: str) -> int | None:
    """Get the timestamp from a Twitch URL"""
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    if 't' in query_params:
        return get_sec(query_params['t'][0])
    return None

# https://youtube.com/watch?v=yzhuCV99Fao&t=319    
# https://www.youtube.com/watch?v=yzhuCV99Fao&t=319
# https://youtu.be/yzhuCV99Fao?t=319
# https://www.youtube.com/shorts/yzhuCV99Fao

def get_youtube_video_id(url: str) -> str:
    """Get the video ID from a YouTube URL
    
    Args:
        url: YouTube URL in any of the supported formats
        
    Returns:
        The YouTube video ID
        
    Raises:
        ValueError: If video ID cannot be extracted from URL
    """
    parsed_url = urlparse(url)
    
    # Handle youtube.com/watch?v=ID format
    if '/watch' in parsed_url.path:
        query_params = parse_qs(parsed_url.query)
        if 'v' in query_params:
            return query_params['v'][0]
    
    # Handle youtu.be/ID format
    elif 'youtu.be' in parsed_url.netloc:
        # Remove leading slash and anything after query parameters
        video_id = parsed_url.path.lstrip('/').split('/')[0]
        if video_id:
            return video_id
    
    # Handle youtube.com/shorts/ID format
    elif '/shorts/' in parsed_url.path:
        video_id = parsed_url.path.split('/shorts/')[1].split('/')[0].split('?')[0]
        if video_id:
            return video_id
    
    raise ValueError(f"Could not extract YouTube video ID from URL: {url}")

# https://www.twitch.tv/videos/123456789?t=1h2m3s
# https://www.twitch.tv/videos/123456789

def get_twitch_video_id(url: str) -> str:
    """Get the video ID from a Twitch URL
    
    Args:
        url: Twitch video URL
        
    Returns:
        The Twitch video ID
        
    Raises:
        ValueError: If video ID cannot be extracted from URL
    """
    parsed_url = urlparse(url)
    
    # Handle twitch.tv/videos/ID format
    if '/videos/' in parsed_url.path:
        # Extract the ID from the path
        video_id = parsed_url.path.split('/videos/')[1].split('/')[0].split('?')[0]
        if video_id and video_id.isdigit():
            return video_id
            
    raise ValueError(f"Could not extract Twitch video ID from URL: {url}")


# https://clips.twitch.tv/CleverClipName
# https://twitch.tv/broadcaster/clip/CleverClipName

def get_twitch_clip_id(url: str) -> str:
    """Get the clip ID from a Twitch URL
    
    Args:
        url: Twitch clip URL
        
    Returns:
        The Twitch clip ID
        
    Raises:
        ValueError: If clip ID cannot be extracted from URL
    """
    parsed_url = urlparse(url)
    
    # Handle clips.twitch.tv/ClipName format
    if '/clips.twitch.tv' in parsed_url.path:
        clip_id = parsed_url.path.lstrip('/').split('/')[0].split('?')[0]
        if clip_id:
            return clip_id
    
    # Handle twitch.tv/broadcaster/clip/ClipName format
    elif '/clip/' in parsed_url.path:
        path_parts = parsed_url.path.split('/clip/')
        if len(path_parts) > 1:
            clip_id = path_parts[1].split('/')[0].split('?')[0]
            if clip_id:
                return clip_id
    
    # Handle embed format with clip parameter
    query_params = parse_qs(parsed_url.query)
    if 'clip' in query_params:
        return query_params['clip'][0]
            
    raise ValueError(f"Could not extract Twitch clip ID from URL: {url}")