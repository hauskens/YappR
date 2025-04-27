from collections.abc import Sequence
from twitchAPI.twitch import Twitch, TwitchUser, Video
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


async def get_latest_broadcasts(twitch_user_id: str) -> Sequence[Video]:
    twitch = await get_twitch_client()
    videos = twitch.get_videos(user_id=twitch_user_id)
    return [video async for video in videos]
