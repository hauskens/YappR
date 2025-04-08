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


def save_thumbnail(thumbnail: Thumbnail, path: str):
    logger.debug(f"Fetching thumbnail, {thumbnail['url']}")
    if not os.path.exists(path):
        response = requests.get(thumbnail["url"])
        if response.status_code == 200:
            with open(path, "wb") as f:
                _ = f.write(response.content)


def save_largest_thumbnail(video: VideoData) -> str | None:
    logger.debug(f"Fetching thumbnails for {video.url}")
    thumbnail = get_largest_thumbnail(video)
    if thumbnail is None:
        return None
    path = config.cache_location + video.id
    save_thumbnail(thumbnail, path)
    logger.info(f"Thumbnail saved {path}")
    return path


def get_yt_videos(channel_url: str) -> list[VideoData] | None:
    yt_opts = {
        "extract_flat": "in_playlist",
        "match_filter": yt_dlp.utils.match_filter_func(
            ["original_url!*=/shorts/ & url!*=/shorts/"], None
        ),
        "noprogress": True,
        "quiet": True,
        "simulate": True,
    }
    videos: list[VideoData] = []
    with yt_dlp.YoutubeDL(yt_opts) as ydl:
        logger.info(f"Fetching videos for {channel_url}")
        info = ydl.extract_info(channel_url)
        if info is not None:
            logger.debug(f"Found {len(info["entries"])} videos on URL: {channel_url}")
            try:
                for i in info["entries"]:
                    try:
                        if "shorts" not in i["webpage_url"]:
                            del i[
                                "__x_forwarded_for_ip"
                            ]  # Remove this because it cant be mapped to VideoData class with __
                            for y in i["entries"]:
                                del y[
                                    "__x_forwarded_for_ip"
                                ]  # Remove this because it cant be mapped to VideoData class with __
                                videos.append(VideoData(**y))
                    except KeyError as e:
                        del i[
                            "__x_forwarded_for_ip"
                        ]  # Remove this because it cant be mapped to VideoData class with __
                        videos.append(VideoData(**i))
            except Exception as e:
                logger.warning(
                    "Tried to map yt-dlp video info to VideoData type, got error: ",
                    e,
                )
            finally:
                logger.info(f"done fetching video info on URL: {channel_url}")
                return videos


def get_yt_video_subtitles(
    video_url: str,
) -> tuple[list[SubtitleData], datetime | None]:
    metadata_location = f"{storage_directory}/{video_url.split('=')[-1]}s.meta"
    yt_opts = {
        "skip_download": True,
        "writeautomaticsub": True,
        "writesubtitles": True,
        "outtmpl": f"{storage_directory}/{video_url.split('=')[-1]}s.%(ext)s",
        "print_to_file": {"video": [("timestamp", metadata_location)]},
    }
    subtitles: list[SubtitleData] = []
    os.remove(metadata_location)
    with yt_dlp.YoutubeDL(yt_opts) as ydl:
        logger.info(f"Fetching subtitles for video: {video_url}")
        data = ydl.extract_info(video_url)
        if data["requested_subtitles"] is not None:
            for subtitle in data["requested_subtitles"]:
                sub = data["requested_subtitles"][subtitle]
                subtitles.append(
                    SubtitleData(
                        video_id=str(data["id"]),
                        extention=sub["ext"],
                        path=sub["filepath"],
                        language=sub["name"],
                    )
                )
    parsedDate = parse_metadata_file(metadata_location)
    return subtitles, parsedDate


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
