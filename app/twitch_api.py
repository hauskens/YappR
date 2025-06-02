from collections.abc import Sequence
from twitchAPI.twitch import Twitch, TwitchUser, Video, SortMethod, VideoType, Clip, CreatedClip
from twitchAPI.helper import first
from .models.config import config
from pytimeparse.timeparse import timeparse
from urllib.parse import urlparse, parse_qs
import re


def parse_time(time_str: str) -> int:
    return timeparse(time_str)

def parse_clip_id(clip_url: str) -> str:
    """
    Extracts the Twitch clip ID from various clip URL formats.
    """
    parsed = urlparse(clip_url)
    path = parsed.path.strip('/')

    # clips.twitch.tv/<clip_id>
    if parsed.netloc == "clips.twitch.tv":
        return path  # the whole path is the clip ID

    # www.twitch.tv/<channel>/clip/<clip_id>
    parts = path.split('/')
    if len(parts) >= 3 and parts[-2] == "clip":
        return parts[-1]
    
    raise ValueError(f"Invalid clip URL: {clip_url}")

def get_twitch_video_id(url: str) -> str:
    """
    Extracts the Twitch video ID from a given URL.

    Supported format:
    - https://www.twitch.tv/videos/123456

    :param url: Twitch video URL
    :return: Video ID
    """
    try:
        parsed = urlparse(url)
        video_id = None

        # Handle short URL (youtu.be)
        if parsed.netloc in ["www.twitch.tv", "twitch.tv"]:
            match = re.match(r"^/videos/(\d+)", path)
            if match:
                video_id = match.group(1)
            else:
                raise ValueError("Failed to get video ID")

        if not video_id:
            raise ValueError("Failed to get video ID")

        return video_id
    except Exception as e:
        raise ValueError(f"Failed to get video ID for url: {url}, exception: {e}")


async def get_twitch_client() -> Twitch:
    if config.twitch_client_id is None or config.twitch_client_secret is None:
        raise ValueError("Twitch client id or secret not configured!")
    return await Twitch(config.twitch_client_id, config.twitch_client_secret)


async def get_twitch_user(twitch_username: str, api_client: Twitch | None = None) -> TwitchUser:
    if api_client is None:
        twitch = await get_twitch_client()
    else:
        twitch = api_client
    user = await first(twitch.get_users(logins=[twitch_username]))
    if user is None:
        raise ValueError(f"Twitch user not found{twitch_username}")
    else:
        return user


async def get_latest_broadcasts(twitch_user_id: str, limit: int = 100, api_client: Twitch | None = None) -> Sequence[Video]:
    if api_client is None:
        twitch = await get_twitch_client()
    else:
        twitch = api_client
    videos = twitch.get_videos(user_id=twitch_user_id, video_type=VideoType.ARCHIVE, sort=SortMethod.TIME, first=limit)
    return [video async for video in videos]


async def get_twitch_video_by_ids(video_ids: list[str], api_client: Twitch | None = None) -> Sequence[Video]:
    if api_client is None:
        twitch = await get_twitch_client()
    else:
        twitch = api_client
    videos = twitch.get_videos(ids=video_ids)
    return [video async for video in videos]

async def get_twitch_clips(clip_ids: list[str], api_client: Twitch | None = None) -> Sequence[Clip]:  
    if api_client is None:
        twitch = await get_twitch_client()
    else:
        twitch = api_client
    clip = twitch.get_clips(clip_id=clip_ids)
    return [clip async for clip in clip]
    
async def create_clip(broadcaster_id: str, api_client: Twitch | None = None) -> CreatedClip:
    if api_client is None:
        twitch = await get_twitch_client()
    else:
        twitch = api_client
    clip = await twitch.create_clip(broadcaster_id=broadcaster_id)
    return clip
