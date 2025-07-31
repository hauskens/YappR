from collections.abc import Sequence
from twitchAPI.twitch import Twitch, TwitchUser, Video, SortMethod, VideoType, Clip, CreatedClip, ChannelModerator, AuthScope, Stream
from twitchAPI.helper import first
from app.models import Users
from app.models.config import config
from pytimeparse.timeparse import timeparse  # type: ignore
from urllib.parse import urlparse
import re
from app.logger import logger


def parse_time(time_str: str) -> int:
    logger.debug("Parsing time: %s", time_str)
    return timeparse(time_str)


def parse_clip_id(clip_url: str) -> str:
    logger.debug("Parsing clip url: %s", clip_url)
    parsed = urlparse(clip_url)
    path = parsed.path.strip('/')

    # clips.twitch.tv/<clip_id>
    if parsed.netloc == "clips.twitch.tv":
        return path  # the whole path is the clip ID

    # www.twitch.tv/<channel>/clip/<clip_id>
    parts = path.split('/')
    if len(parts) >= 3 and parts[-2] == "clip":
        return parts[-1]
    logger.error("Invalid clip URL: %s", clip_url)
    raise ValueError(f"Invalid clip URL: {clip_url}")


def get_twitch_video_id(url: str) -> str:
    """
    Extracts the Twitch video ID from a given URL.

    Supported format:
    - https://www.twitch.tv/videos/123456

    :param url: Twitch video URL
    :return: Video ID
    """
    logger.debug("Parsing video url: %s", url)
    try:
        parsed = urlparse(url)
        video_id = None

        # Handle short URL (youtu.be)
        if parsed.netloc in ["www.twitch.tv", "twitch.tv"]:
            match = re.match(r"^/videos/(\d+)", parsed.geturl())
            if match:
                video_id = match.group(1)
            else:
                logger.error("Failed to get video ID for url: %s", url)
                raise ValueError("Failed to get video ID")

        if not video_id:
            logger.error("Failed to get video ID for url: %s", url)
            raise ValueError("Failed to get video ID")

        return video_id
    except Exception as e:
        logger.error(
            "Failed to get video ID for url: %s, exception: %s", url, e)
        raise ValueError(
            f"Failed to get video ID for url: {url}, exception: {e}")


async def get_twitch_client() -> Twitch:
    """Legacy function for backward compatibility. Use TwitchClientFactory.get_server_client() instead."""
    from app.twitch_client_factory import TwitchClientFactory
    return await TwitchClientFactory.get_server_client()


async def get_twitch_client_for_user(user: Users) -> Twitch:
    """Get Twitch client authenticated with user's OAuth token."""
    from app.twitch_client_factory import TwitchClientFactory
    return await TwitchClientFactory.get_user_client(user)


async def get_twitch_client_for_bot() -> Twitch:
    """Get Twitch client authenticated with bot's OAuth token."""
    from app.twitch_client_factory import TwitchClientFactory
    return await TwitchClientFactory.get_bot_client()


async def get_twitch_user(twitch_username: str, api_client: Twitch | None = None) -> TwitchUser:
    if api_client is None:
        twitch = await get_twitch_client()
    else:
        twitch = api_client
    logger.info("Getting twitch user: %s", twitch_username)
    user = await first(twitch.get_users(logins=[twitch_username]))
    logger.debug("Got twitch user: %s", user)
    if user is None:
        logger.error("Twitch user not found: %s", twitch_username)
        raise ValueError(f"Twitch user not found{twitch_username}")
    else:
        return user


async def get_twitch_user_by_id(twitch_user_id: str, api_client: Twitch | None = None) -> TwitchUser:
    if api_client is None:
        twitch = await get_twitch_client()
    else:
        twitch = api_client
    logger.info("Getting twitch user by id: %s", twitch_user_id)
    users = await first(twitch.get_users(user_ids=[twitch_user_id]))
    logger.debug("Got twitch user by id: %s", users)
    if users is None:
        logger.error("Twitch users not found: %s", twitch_user_id)
        raise ValueError(f"Twitch users not found{twitch_user_id}")
    else:
        return users


async def get_current_live_streams(twitch_user_ids: list[str], api_client: Twitch | None = None) -> list[Stream]:
    if api_client is None:
        twitch = await get_twitch_client()
    else:
        twitch = api_client
    logger.info("Getting twitch users by ids: %s", twitch_user_ids)
    streams = twitch.get_streams(user_id=twitch_user_ids)
    if streams is None:
        logger.error("Twitch users not found: %s", twitch_user_ids)
        raise ValueError(f"Twitch users not found{twitch_user_ids}")
    else:
        return [stream async for stream in streams]


async def get_twitch_users_by_ids(twitch_user_ids: list[str], api_client: Twitch | None = None) -> list[TwitchUser]:
    if api_client is None:
        twitch = await get_twitch_client()
    else:
        twitch = api_client
    logger.info("Getting twitch users by ids: %s", twitch_user_ids)
    users = twitch.get_users(user_ids=twitch_user_ids)
    if users is None:
        logger.error("Twitch users not found: %s", twitch_user_ids)
        raise ValueError(f"Twitch users not found{twitch_user_ids}")
    else:
        return [user async for user in users]


async def get_latest_broadcasts(twitch_user_id: str, limit: int = 100, api_client: Twitch | None = None) -> Sequence[Video]:
    if api_client is None:
        twitch = await get_twitch_client()
    else:
        twitch = api_client
    logger.info("Getting latest broadcasts for user id: %s", twitch_user_id)
    videos = twitch.get_videos(
        user_id=twitch_user_id, video_type=VideoType.ARCHIVE, sort=SortMethod.TIME, first=limit)
    logger.debug("Got latest broadcasts for user id: %s", twitch_user_id)
    return [video async for video in videos]


async def get_twitch_video_by_ids(video_ids: list[str], api_client: Twitch | None = None) -> Sequence[Video]:
    if api_client is None:
        twitch = await get_twitch_client()
    else:
        twitch = api_client
    logger.info("Getting twitch video by ids: %s", video_ids)
    videos = twitch.get_videos(ids=video_ids)
    logger.debug("Got twitch video by ids: %s", video_ids)
    return [video async for video in videos]


async def get_twitch_clips(clip_ids: list[str], api_client: Twitch | None = None) -> Sequence[Clip]:
    if api_client is None:
        twitch = await get_twitch_client()
    else:
        twitch = api_client
    logger.info("Getting twitch clips by ids: %s", clip_ids)
    clip = twitch.get_clips(clip_id=clip_ids)
    logger.debug("Got twitch clips by ids: %s", clip_ids)
    return [clip async for clip in clip]


async def create_clip(broadcaster_id: str, api_client: Twitch | None = None) -> CreatedClip:
    if api_client is None:
        twitch = await get_twitch_client()
    else:
        twitch = api_client
    logger.info("Creating clip for broadcaster id: %s", broadcaster_id)
    clip = await twitch.create_clip(broadcaster_id=broadcaster_id)
    logger.debug("Created clip for broadcaster id: %s", broadcaster_id)
    return clip


async def get_moderated_channels(twitch_user_id: str, api_client: Twitch | None = None) -> Sequence[ChannelModerator]:
    if api_client is None:
        twitch = await get_twitch_client()
    else:
        twitch = api_client
    logger.info(
        "Getting twitch moderated channels for user id: %s", twitch_user_id)
    moderators = twitch.get_moderated_channels(user_id=twitch_user_id)
    logger.debug("Got twitch moderated channels for user id: %s",
                 twitch_user_id)
    return [moderator async for moderator in moderators]
