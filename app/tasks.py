import yt_dlp
from yt_dlp.utils import download_range_func
from .models.yt import VideoData, SubtitleData, Thumbnail
from .models.config import Config
import logging
import os
import requests
from datetime import datetime


logger = logging.getLogger(__name__)
storage_directory = os.path.abspath(Config().cache_location)
config = Config()


def parse_metadata_file(path: str) -> datetime | None:
    logger.debug(f"Parsing metadata on file: {path}")
    with open(path) as file:
        for line in file:
            date_str = line.strip()  # Remove leading/trailing whitespace
            try:
                result = datetime.utcfromtimestamp(int(date_str))
                if result is not None:
                    logger.info(f"Found metadata on file: {path} - {result}")
                    return result
            except ValueError:  # Ignore invalid dates
                pass


def get_largest_thumbnail(video: VideoData) -> Thumbnail | None:
    if video.thumbnails:
        if len(video.thumbnails) > 0:
            result = video.thumbnails.pop()
            logger.debug(f"Found thumbnail, {result}")
            return result
    else:
        raise ValueError("Video has no thumbnails")


def get_yt_segment(video_url: str, start_time: int, duration: int) -> str:
    storage_directory = "."
    download_path: str = (
        f"{storage_directory}/{video_url.split('=')[-1]}_{start_time}_{duration}_clip.%(ext)s"
    )
    yt_opts = {
        "outtmpl": download_path,
        "format": "best[ext=mp4]",
        "force_keyframes_at_cuts": True,
        "verbose": True,
        "download_ranges": download_range_func(
            None, [(start_time, start_time + duration)]
        ),
    }
    with yt_dlp.YoutubeDL(yt_opts) as ydl:
        logger.info(
            f"Fetching clip for video: {video_url}, starting at {start_time}s and ending at {duration}s"
        )
        _ = ydl.extract_info(video_url)
        logger.info(
            f"Done: {video_url}, starting at {start_time}s and ending at {duration}s"
        )
        return download_path


def get_yt_audio(video_url: str) -> str:
    download_path: str = f"{storage_directory}/{video_url.split('=')[-1]}s.webm"

    yt_opts = {
        "extract_audio": True,
        "format": "bestaudio[ext=webm]",
        "outtmpl": download_path,
    }
    with yt_dlp.YoutubeDL(yt_opts) as ydl:
        logger.info(f"Fetching audio for video: {video_url}")
        _ = ydl.download(video_url)
        return download_path


if __name__ == "__main__":
    get_yt_segment("", 30, 20)
