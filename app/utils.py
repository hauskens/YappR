# originally inspired by https://github.com/lawrencehook/SqueexVodSearch/blob/main/preprocessing/scripts/parse.py

import re
import os
import requests
from datetime import datetime, timedelta
from app.models.config import config
from twitchAPI.twitch import Video
from app.logger import logger
from urllib.parse import urlparse, parse_qs
from pydantic import HttpUrl
import nltk  # type: ignore
from nltk.corpus import stopwords  # type: ignore
from nltk.tag import pos_tag  # type: ignore
from nltk.tokenize import word_tokenize  # type: ignore
from nltk.stem import PorterStemmer  # type: ignore
from typing import Tuple
from app.logger import logger

def download_nltk() -> None:
    """Download NLTK data if not already downloaded"""
    nltk.download("stopwords", quiet=True)
    nltk.download("punkt_tab", quiet=True)
    nltk.download("averaged_perceptron_tagger_eng", quiet=True)




# This function is used by both parsing and searching to ensure we are getting good search results.
def sanitize_sentence(sentence: str) -> list[str]:
    sw = stopwords.words("english")
    words = pos_tag(word_tokenize(sentence))
    ps = PorterStemmer()
    result: list[str] = []
    for word in words:
        if word[0] not in sw:
            word = ps.stem(word[0])
            result.append(word)
    return result


def seconds_to_string(seconds: int | float) -> str:
    return str(timedelta(seconds=int(seconds)))


def loosely_sanitize_sentence(sentence: str) -> list[str]:
    sw = stopwords.words("english")
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


def format_duration_to_srt_timestamp(seconds):
    """
    Format seconds to SRT timestamp format (HH:MM:SS,mmm).

    Args:
        seconds: Time in seconds (can be a float)

    Returns:
        str: Formatted timestamp
    """
    # Convert to string with 3 decimal places and parse manually to avoid rounding errors
    time_str = f"{seconds:.3f}"
    whole, frac = time_str.split('.')

    milliseconds = frac

    total_seconds = int(whole)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60

    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds}"


def save_generic_thumbnail(url: HttpUrl, force: bool = False) -> str:
    """Save a generic thumbnail from a URL. 
    Returns the path to the thumbnail. 
    If thumbnail already exists in cache, returns the path to the existing thumbnail.

    Args:
        url: The URL of the thumbnail
        force: Whether to force the download of the thumbnail (overrides cached thumbnail)
    """
    # Create a safe filename using hash of the URL
    import hashlib
    url_str = url.__str__()
    # Get file extension from URL if available
    file_ext = os.path.splitext(url_str.split('?')[0])[1] or '.jpg'
    if file_ext not in ['.jpg', '.png', '.jpeg', '.webp', '.gif', '.bmp', '.tiff', '.svg', '.ico']:
        raise ValueError(f"Unsupported file extension: {file_ext}")
    # Create hash of URL for a safe, unique filename
    url_hash = hashlib.md5(url_str.encode()).hexdigest()
    safe_filename = f"{url_hash}{file_ext}"
    
    # Ensure cache directory exists
    os.makedirs(config.cache_location, exist_ok=True)
    
    # Create full path
    path = os.path.join(config.cache_location, safe_filename)
    
    if not os.path.exists(path) or force:
        response = requests.get(url_str)
        if response.status_code == 200:
            with open(path, "wb") as f:
                _ = f.write(response.content)
            return path
    return path


def get_youtube_thumbnail_url(video_ref: str) -> HttpUrl:
    """
    Get the highest quality YouTube thumbnail URL for a given video ID.

    Args:
        video_id (str): YouTube video ID

    Returns:
        str: URL of the highest quality thumbnail available
    """
    # YouTube thumbnail quality options in descending order of quality
    quality_options = [
        'maxresdefault',  # 1280x720
        'sddefault',      # 640x480
        'hqdefault',      # 480x360
        'mqdefault',      # 320x180
        'default'         # 120x90
    ]

    base_url = f"https://img.youtube.com/vi/{video_ref}/"

    # Try each quality option, starting with highest
    for quality in quality_options:
        thumbnail_url = f"{base_url}{quality}.jpg"

        try:
            # Check if the thumbnail exists by making a HEAD request
            save_generic_thumbnail(HttpUrl(thumbnail_url))
            return HttpUrl(thumbnail_url)
        except Exception:
            # If request fails, continue to next quality option
            continue

    # Fallback to default if all else fails
    return HttpUrl(f"{base_url}default.jpg")


def get_twitch_thumbnail_url(video: Video, force: bool = False) -> HttpUrl:
    thumbnail = video.thumbnail_url
    thumbnail_url = thumbnail.replace("%{width}", str(320)).replace(
        "%{height}", str(180)
    )
    logger.debug("Fetching thumbnail, %s", thumbnail_url)
    return HttpUrl(thumbnail_url)


def get_valid_date(date_string: str) -> datetime | None:
    try:
        date = datetime.strptime(date_string, "%Y-%m-%d")
        return date
    except ValueError:
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
        video_id = parsed_url.path.split(
            '/shorts/')[1].split('/')[0].split('?')[0]
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
        video_id = parsed_url.path.split(
            '/videos/')[1].split('/')[0].split('?')[0]
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


class TitleDateParser:
    """
    Parser for extracting dates from video titles in various formats.
    Supports multiple date formats commonly used in stream VOD titles.
    """
    
    def __init__(self):
        self.date_patterns = [
            # YYYY.MM.DD format: '2025.05.07 fanfan - amogus 3d'
            (r'(\d{4})\.(\d{1,2})\.(\d{1,2})', self._parse_ymd_dot),
            
            # [Mon DD(th|st|nd|rd)?, 'YY] format: '[Jan 24th, '25] Tombs of...'
            (r'\[([A-Za-z]{3})\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+\'(\d{2})\]', self._parse_month_day_year_bracket),
            
            # [MM/DD/YY] format: '[10/28/24] Stream VOD'
            (r'\[(\d{1,2})/(\d{1,2})/(\d{2})\]', self._parse_mdy_slash_bracket),
            
            # MM/DD/YYYY format: '10/28/2024 Stream'
            (r'(\d{1,2})/(\d{1,2})/(\d{4})', self._parse_mdy_slash),
            
            # YYYY-MM-DD format: '2025-01-15 Stream'
            (r'(\d{4})-(\d{1,2})-(\d{1,2})', self._parse_ymd_dash),
            
            # Month DD, YYYY format: 'January 15, 2025 Stream'
            (r'([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})', self._parse_month_name_day_year),
            
            # DD Month YYYY format: '15 January 2025 Stream'
            (r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', self._parse_day_month_name_year),
        ]
        
        self.month_names = {
            'jan': 1, 'january': 1,
            'feb': 2, 'february': 2,
            'mar': 3, 'march': 3,
            'apr': 4, 'april': 4,
            'may': 5,
            'jun': 6, 'june': 6,
            'jul': 7, 'july': 7,
            'aug': 8, 'august': 8,
            'sep': 9, 'september': 9,
            'oct': 10, 'october': 10,
            'nov': 11, 'november': 11,
            'dec': 12, 'december': 12,
        }
    
    def extract_date_from_title(self, title: str) -> datetime | None:
        """
        Extract date from video title using various patterns.
        Returns the first valid date found, or None if no date is found.
        """
        for pattern, parser_func in self.date_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                try:
                    date_obj = parser_func(match.groups())
                    if date_obj:
                        logger.info(f"Extracted date {date_obj} from title: '{title[:50]}...'")
                        return date_obj
                except (ValueError, IndexError) as e:
                    logger.debug(f"Failed to parse date with pattern {pattern}: {e}")
                    continue
        
        logger.debug(f"No date found in title: '{title[:50]}...'")
        return None
    
    def _parse_ymd_dot(self, groups: Tuple[str, ...]) -> datetime | None:
        """Parse YYYY.MM.DD format"""
        year, month, day = groups
        return datetime(int(year), int(month), int(day))
    
    def _parse_month_day_year_bracket(self, groups: Tuple[str, ...]) -> datetime | None:
        """Parse [Mon DD, 'YY] format"""
        month_str, day, year = groups
        month = self.month_names.get(month_str.lower())
        if not month:
            return None
        # Convert 2-digit year to 4-digit (assuming 2000s)
        full_year = 2000 + int(year)
        return datetime(full_year, month, int(day))
    
    def _parse_mdy_slash_bracket(self, groups: Tuple[str, ...]) -> datetime | None:
        """Parse [MM/DD/YY] format"""
        month, day, year = groups
        # Convert 2-digit year to 4-digit (assuming 2000s)
        full_year = 2000 + int(year)
        return datetime(full_year, int(month), int(day))
    
    def _parse_mdy_slash(self, groups: Tuple[str, ...]) -> datetime | None:
        """Parse MM/DD/YYYY format"""
        month, day, year = groups
        return datetime(int(year), int(month), int(day))
    
    def _parse_ymd_dash(self, groups: Tuple[str, ...]) -> datetime | None:
        """Parse YYYY-MM-DD format"""
        year, month, day = groups
        return datetime(int(year), int(month), int(day))
    
    def _parse_month_name_day_year(self, groups: Tuple[str, ...]) -> datetime | None:
        """Parse 'Month DD, YYYY' format"""
        month_str, day, year = groups
        month = self.month_names.get(month_str.lower())
        if not month:
            return None
        return datetime(int(year), month, int(day))
    
    def _parse_day_month_name_year(self, groups: Tuple[str, ...]) -> datetime | None:
        """Parse 'DD Month YYYY' format"""
        day, month_str, year = groups
        month = self.month_names.get(month_str.lower())
        if not month:
            return None
        return datetime(int(year), month, int(day))


def extract_date_from_video_title(title: str) -> datetime | None:
    """
    Convenience function to extract date from video title.
    Returns the parsed date or None if no date found.
    """
    parser = TitleDateParser()
    return parser.extract_date_from_title(title)