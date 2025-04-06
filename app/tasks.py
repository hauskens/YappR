import yt_dlp
from models.yt import VideoData, SubtitleData
import logging

logger = logging.getLogger(__name__)


def get_yt_videos(channel_url: str) -> list[VideoData] | None:
    yt_opts = {
        "extract_flat": "in_playlist",
        # "skip_download": True,
        # "match_filter": yt_dlp.utils.match_filter_func(
        #     ["original_url!*=/shorts/ & url!*=/shorts/"], None
        # ),
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
            for i in info["entries"]:
                del i[
                    "__x_forwarded_for_ip"
                ]  # Remove this because it cant be mapped to VideoData class with __
                try:
                    videos.append(VideoData(**i))
                except TypeError as e:
                    logger.error(
                        "Tried to map yt-dlp video info to VideoData type, got error: ",
                        e,
                    )
    return videos


def get_yt_video_subtitles(
    video_url: str, storage_directory: str
) -> list[SubtitleData]:
    yt_opts = {
        "skip_download": True,
        "writeautomaticsub": True,
        "writesubtitles": True,
        "outtmpl": f"{storage_directory}/{video_url.split('=')[-1]}s.%(ext)s",
    }
    subtitles: list[SubtitleData] = []
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
    return subtitles


if __name__ == "__main__":
    get_yt_video_subtitles("https://www.youtube.com/watch?v=leRys8FOYd0", "./test")
