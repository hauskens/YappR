# import enum
# from typing import Iterable
# from sqlalchemy import (
#     Boolean,
#     ForeignKey,
#     String,
#     Integer,
#     Enum,
#     Float,
#     DateTime,
#     Text,
#     Computed,
#     Index,
#     UniqueConstraint,
#     BigInteger,
# )
# from sqlalchemy import select, func
# from sqlalchemy.dialects.postgresql import JSON
# from sqlalchemy.orm import Mapped, mapped_column, relationship
# from sqlalchemy_file import FileField, File
# from datetime import datetime, timedelta
# from twitchAPI.twitch import ChannelModerator as TwitchChannelModerator
# from app.cache import cache
# from io import BytesIO
# import webvtt  # type: ignore
# import re
# import asyncio
# import json
# from app.logger import logger
# from typing import Literal
# from app.shared import convert_to_srt

# from .transcription import TranscriptionResult
# from .config import config
# from ..utils import (
#     get_sec,
#     save_yt_thumbnail,
#     save_twitch_thumbnail,
#     seconds_to_string,
# )
# from ..youtube_api import (
#     get_youtube_channel_details,
#     get_videos_on_channel,
#     get_all_videos_on_channel,
#     get_videos,
#     fetch_transcription,
# )
# from ..tasks import get_twitch_audio, get_yt_audio
# from ..twitch_api import get_twitch_user, get_twitch_user_by_id, get_latest_broadcasts, get_twitch_video_by_ids, parse_time, get_moderated_channels

# from .youtube.search import SearchResultItem
# from youtube_transcript_api.formatters import WebVTTFormatter
# from .base import Base
# from . import db
# from app.platforms.handler import PlatformRegistry






