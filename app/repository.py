import logging
import os
import requests
from youtube_transcript_api.formatters import WebVTTFormatter
from .models.db import (
    VideoType,
    db,
    Channels,
    Video,
    Transcription,
    TranscriptionSource,
)
from .models.config import config
from .models.youtube.search import SearchResultItem
from .models.youtube.video import VideoDetails
from .youtube_api import (
    get_youtube_channel_details,
    get_videos_on_channel,
    get_videos,
    fetch_transcription,
)
from .retrievers import get_video_by_ref, get_video

logger = logging.getLogger(__name__)


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
    raise (ValueError(f"Failed to download thumbnail for video {video.id}"))


def save_transcription(video_id: int):
    video = get_video(video_id)
    formatter = WebVTTFormatter()
    path = config.cache_location + video.platform_ref + ".vtt"
    transcription = fetch_transcription(video.platform_ref)
    t_formatted = formatter.format_transcript(transcription)
    with open(path, "w", encoding="utf-8") as vtt_file:
        _ = vtt_file.write(t_formatted)
    if len(video.transcriptions) == 0:
        logger.info(f"transcriptions not found on {video_id}, adding new..")
        db.session.add(
            Transcription(
                video_id=video_id,
                language=transcription.language,
                file_extention="vtt",
                file=open(path, "rb"),
                source=TranscriptionSource.YouTube,
            )
        )
        db.session.commit()


class Channel:
    db_ref: Channels

    def __init__(self, channel_id: int):
        self.db_ref = db.session.query(Channels).filter_by(id=channel_id).one()

    def get(self) -> Channels:
        return self.db_ref

    def update(self):
        result = get_youtube_channel_details(self.db_ref.platform_ref)
        self.db_ref.platform_channel_id = result.id
        db.session.commit()

    def delete(self):
        _ = db.session.query(Channels).filter_by(id=self.db_ref.id).delete()
        db.session.commit()

    def fetch_latest_videos(self):
        if (
            self.db_ref.platform.name.lower() == "youtube"
            and self.db_ref.platform_channel_id is not None
        ):
            latest_videos = get_videos_on_channel(self.db_ref.platform_channel_id)
            videos_result: list[SearchResultItem] = []
            for search_result in latest_videos.items:
                existing_video = get_video_by_ref(search_result.id.videoId)
                if existing_video is None:
                    videos_result.append(search_result)

            videos_details = get_videos([item.id.videoId for item in videos_result])
            for video in videos_details:
                tn = save_thumbnail(video)
                db.session.add(
                    Video(
                        title=video.snippet.title,
                        video_type=VideoType.VOD,
                        channel_id=self.db_ref.id,
                        platform_ref=video.id,
                        duration=video.contentDetails.duration.total_seconds(),
                        uploaded=video.snippet.publishedAt,
                        thumbnail=open(tn, "rb"),
                    )
                )
        db.session.commit()
