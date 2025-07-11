# originally inspired by https://github.com/lawrencehook/SqueexVodSearch/blob/main/preprocessing/scripts/parse.py

import re
import os
import requests
from datetime import datetime, timedelta
from app.models.youtube.video import VideoDetails
from app.models.config import config
from twitchAPI.twitch import Video
from app.logger import logger

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
    """Get seconds from time."""
    h, m, s = re.sub(r"\..*$", "", time_str).split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


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
