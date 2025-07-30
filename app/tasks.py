import yt_dlp  # type: ignore
from yt_dlp.utils import download_range_func  # type: ignore
import glob
from .models.yt import VideoData, Thumbnail
import os
from .models.config import config
from app.logger import logger
from .models.utils import ProgressCallbackType


storage_directory = os.path.abspath(config.cache_location)


def get_largest_thumbnail(video: VideoData) -> Thumbnail:
    if video.thumbnails:
        if len(video.thumbnails) > 0:
            result = video.thumbnails.pop()
            logger.debug("Found thumbnail %s", result)
            return result
        else:
            logger.error("Video has thumbnails list but it's empty")
            raise ValueError("Video has thumbnails list but it's empty")
    else:
        logger.error("Video has no thumbnails")
        raise ValueError("Video has no thumbnails")


def find_downloaded_file(storage_directory: str, video_url: str) -> str:
    # if video_url contains youtube, use the video_id
    logger.debug("Finding downloaded file for %s", video_url)
    if "youtube" in video_url:
        prefix = f"{video_url.split('=')[-1]}s"
    elif "twitch" in video_url:
        prefix = f"{video_url.split('/')[-1]}s"
    else:
        raise ValueError("Unknown video_url")
    search_pattern = os.path.join(storage_directory, f"{prefix}.*")
    matches = glob.glob(search_pattern)

    if not matches:
        logger.error("No file found matching: %s", search_pattern)
        raise FileNotFoundError(f"No file found matching: {search_pattern}")

    return matches[0]


def get_yt_segment(video_url: str, start_time: int, duration: int) -> str:
    storage_directory = "."
    logger.debug("Fetching segment for %s", video_url)
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
            "Fetching clip for video: %s, starting at %ss and ending at %ss",
            video_url,
            start_time,
            duration,
        )
        _ = ydl.extract_info(video_url)
        logger.info(
            "Done: %s, starting at %ss and ending at %ss",
            video_url,
            start_time,
            duration,
        )
        return download_path


def get_yt_audio(video_url: str, progress_callback: ProgressCallbackType | None = None) -> str:
    download_path: str = f"{storage_directory}/{video_url.split('=')[-1]}s.%(ext)s"
    cookie_path: str = f"{storage_directory}/cookies.txt"

    yt_opts = {
        "extract_audio": True,
        "format": "bestaudio[resolution='audio only']",
        "outtmpl": download_path,
    }

    if os.path.exists(cookie_path):
        yt_opts["cookiefile"] = cookie_path
    
    if progress_callback:
        yt_opts["progress_hooks"] = [progress_callback]

    logger.info("Fetching audio for video: %s", video_url)
    with yt_dlp.YoutubeDL(yt_opts) as ydl:
        _ = ydl.download(video_url)
        return find_downloaded_file(storage_directory, video_url)


def get_twitch_audio(video_url: str, progress_callback: ProgressCallbackType | None = None) -> str:
    download_path: str = f"{storage_directory}/{video_url.split('/')[-1]}s.%(ext)s"

    twitch_opts = {
        "format": "all[resolution='audio only']",
        "match_filter": yt_dlp.utils.match_filter_func(['!is_live'], None),
        "outtmpl": download_path,
    }
    
    if progress_callback:
        twitch_opts["progress_hooks"] = [progress_callback]

    logger.info("Fetching audio for video: %s", video_url)
    with yt_dlp.YoutubeDL(twitch_opts) as ydl:
        _ = ydl.download(video_url)
        return find_downloaded_file(storage_directory, video_url)


def get_twitch_segment(video_url: str, start_time: int, duration: int) -> str:
    clips_directory = os.path.join(storage_directory, "clips")
    os.makedirs(clips_directory, exist_ok=True)

    logger.debug("Fetching Twitch segment for %s", video_url)
    video_id = video_url.split('/')[-1]
    clip_basename = f"{video_id}_{start_time}_{duration}_clip"
    download_path: str = f"{clips_directory}/{clip_basename}.%(ext)s"

    # Calculate end time in seconds
    end_time = start_time + duration

    twitch_opts = {
        "outtmpl": download_path,
        "format": "best",
        "force_keyframes_at_cuts": True,
        "verbose": True,
        "match_filter": yt_dlp.utils.match_filter_func(['!is_live'], None),
        "download_ranges": download_range_func([], [[float(start_time), float(end_time)]]),
    }

    with yt_dlp.YoutubeDL(twitch_opts) as ydl:
        logger.info(
            "Fetching Twitch clip for video: %s, from %ss to %ss",
            video_url,
            start_time,
            end_time,
        )
        _ = ydl.extract_info(video_url)
        logger.info(
            "Done: Twitch clip for %s, from %ss to %ss",
            video_url,
            start_time,
            end_time,
        )

        # Return the basename pattern for file checking
        return clip_basename
