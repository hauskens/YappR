from collections.abc import Sequence
from twitchAPI.twitch import Twitch, TwitchUser, Video, SortMethod, VideoType
from twitchAPI.helper import first
from .models.config import config
from pytimeparse.timeparse import timeparse


def parse_time(time_str: str) -> int:
    return timeparse(time_str)


async def get_twitch_client() -> Twitch:
    if config.twitch_client_id is None or config.twitch_client_secret is None:
        raise ValueError("Twitch client id or secret not configured!")
    return await Twitch(config.twitch_client_id, config.twitch_client_secret)


async def get_twitch_user(twitch_username: str) -> TwitchUser:
    twitch = await get_twitch_client()
    user = await first(twitch.get_users(logins=[twitch_username]))
    if user is None:
        raise ValueError(f"Twitch user not found{twitch_username}")
    else:
        return user


async def get_latest_broadcasts(twitch_user_id: str, limit: int = 100) -> Sequence[Video]:
    twitch = await get_twitch_client()
    videos = twitch.get_videos(user_id=twitch_user_id, video_type=VideoType.ARCHIVE, sort=SortMethod.TIME, first=limit)
    return [video async for video in videos]
