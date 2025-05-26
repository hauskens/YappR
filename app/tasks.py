import yt_dlp
from yt_dlp.utils import download_range_func
import glob
from .models.yt import VideoData, Thumbnail
import logging
import os
from .models.config import config
from datetime import datetime


logger = logging.getLogger(__name__)
storage_directory = os.path.abspath(config.cache_location)


def get_largest_thumbnail(video: VideoData) -> Thumbnail | None:
    if video.thumbnails:
        if len(video.thumbnails) > 0:
            result = video.thumbnails.pop()
            logger.debug(f"Found thumbnail, {result}")
            return result
    else:
        raise ValueError("Video has no thumbnails")

def find_downloaded_file(storage_directory: str, video_url: str) -> str:
    # if video_url contains youtube, use the video_id
    if "youtube" in video_url:
        prefix = f"{video_url.split('=')[-1]}s"
    elif "twitch" in video_url:
        prefix = f"{video_url.split('/')[-1]}s"
    else:
        raise ValueError("Unknown video_url")
    search_pattern = os.path.join(storage_directory, f"{prefix}.*")
    matches = glob.glob(search_pattern)
    
    if not matches:
        raise FileNotFoundError(f"No file found matching: {search_pattern}")
    
    return matches[0]

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
    download_path: str = f"{storage_directory}/{video_url.split('=')[-1]}s.%(ext)s"
    cookie_path: str = f"{storage_directory}/cookies.txt"

    yt_opts = {
        "extract_audio": True,
        "format": "bestaudio[resolution='audio only']",
        "outtmpl": download_path,
    }

    if os.path.exists(cookie_path):
        yt_opts["cookiefile"] = cookie_path


    with yt_dlp.YoutubeDL(yt_opts) as ydl:
        logger.info(f"Fetching audio for video: {video_url}")
        _ = ydl.download(video_url)
        return find_downloaded_file(storage_directory, video_url)


def get_twitch_audio(video_url: str) -> str:
    download_path: str = f"{storage_directory}/{video_url.split('/')[-1]}s.%(ext)s"

    twitch_opts = {
        "format": "all[resolution='audio only']",
        "match_filter": yt_dlp.utils.match_filter_func(['!is_live'], None),
        "outtmpl": download_path,
    }

    with yt_dlp.YoutubeDL(twitch_opts) as ydl:
        logger.info(f"Fetching audio for video: {video_url}")
        _ = ydl.download(video_url)
        return find_downloaded_file(storage_directory, video_url)
