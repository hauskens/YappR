# originally inspired by https://github.com/lawrencehook/SqueexVodSearch/blob/main/preprocessing/scripts/parse.py

import logging
import re
import nltk
import os
import requests
from datetime import datetime, timedelta
from nltk.corpus import stopwords
from nltk.tag import pos_tag
from nltk.tokenize import word_tokenize
from nltk.stem import PorterStemmer
from .models.youtube.video import VideoDetails
from .models.config import config
from twitchAPI.twitch import Video
from typing import Callable, Any, TypeVar, cast
from functools import wraps
from flask import request, abort

if not nltk.data.path:
    _ = nltk.download("stopwords")
    _ = nltk.download("averaged_perceptron_tagger_eng")
    _ = nltk.download("punkt_tab")

sw = stopwords.words("english")
ps = PorterStemmer()
logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

def require_api_key(func: F) -> F:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        key: str | None = request.headers.get("X-API-Key")
        if key != config.api_key:
            abort(401, description="Invalid or missing API key.")
        return func(*args, **kwargs)
    return cast(F, wrapper)

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
    """Get seconds from time."""
    h, m, s = re.sub(r"\..*$", "", time_str).split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def save_yt_thumbnail(video: VideoDetails, force: bool = False) -> str:
    path = config.cache_location + video.id
    thumbnail = video.snippet.thumbnails.get("high")
    if thumbnail is None:
        thumbnail = video.snippet.thumbnails.get("default")
    if thumbnail is not None or force:
        logger.debug(f"Fetching thumbnail, {thumbnail.url}")
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
    logger.debug(f"Fetching thumbnail, {thumbnail_url}")
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
        logger.warning(f"didnt match date on {date_string}")
        return
