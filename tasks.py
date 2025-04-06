import yt_dlp
from models.yt import VideoData
import logging

logger = logging.getLogger(__name__)

yt_opts = {
    "extract_flat": "in_playlist",
    "match_filter": yt_dlp.utils.match_filter_func(
        ["original_url!*=/shorts/ & url!*=/shorts/"], None
    ),
    "noprogress": True,
    "quiet": True,
    "simulate": True,
}


def get_yt_videos(channel_url: str) -> list[VideoData] | None:
    videos: list[VideoData] = []
    with yt_dlp.YoutubeDL(yt_opts) as ydl:
        logger.info(f"Fetching videos for {channel_url}")
        info = ydl.extract_info(channel_url)
        if info is not None:
            logger.debug(f"Found {len(info["entries"])} videos on URL: {channel_url}")
            for i in info["entries"]:
                del i[
                    "__x_forwarded_for_ip"
                ]  # Remove this because it cant be mapped to VideoData class with __
                videos.append(VideoData(**i))
    return videos
