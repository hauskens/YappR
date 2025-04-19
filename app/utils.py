# originally inspired by https://github.com/lawrencehook/SqueexVodSearch/blob/main/preprocessing/scripts/parse.py

import logging
import re
import nltk
import os
import requests
from datetime import datetime
from nltk.corpus import stopwords
from nltk.tag import pos_tag
from nltk.tokenize import word_tokenize
from nltk.stem import PorterStemmer
from .models.youtube.video import VideoDetails
from .models.config import config

_ = nltk.download("stopwords")
_ = nltk.download("averaged_perceptron_tagger_eng")
_ = nltk.download("punkt_tab")

sw = stopwords.words("english")
ps = PorterStemmer()
logger = logging.getLogger(__name__)


# This function is used by both parsing and searching to ensure we are getting good search results.
def sanitize_sentence(sentence: str) -> list[str]:
    words = pos_tag(word_tokenize(sentence))
    result: list[str] = []
    for word in words:
        if word[0] not in sw:
            word = ps.stem(word[0])
            result.append(word)
    return result


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


def save_thumbnail(video: VideoDetails) -> str:
    path = config.cache_location + video.id
    thumbnail = video.snippet.thumbnails.get("high")
    if thumbnail is None:
        thumbnail = video.snippet.thumbnails.get("default")
    if thumbnail is not None:
        logger.debug(f"Fetching thumbnail, {thumbnail.url}")
        if not os.path.exists(path):
            response = requests.get(thumbnail.url)
            if response.status_code == 200:
                with open(path, "wb") as f:
                    _ = f.write(response.content)
                return path
        return path
    raise (ValueError(f"Failed to download thumbnail for video {video.id}"))


def get_valid_date(date_string: str) -> datetime | None:
    try:
        date = datetime.strptime(date_string, "%Y-%m-%d")
        return date
    except ValueError:
        logger.warning(f"didnt match date on {date_string}")
        return
