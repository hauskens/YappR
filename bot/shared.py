from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, scoped_session
from app.models.db import OAuth, Channels, ChannelSettings, ChatLog, Content, ContentQueue, ContentQueueSubmission, ExternalUser, AccountSource
from app.models.config import config
from app.twitch_api import parse_clip_id, get_twitch_clips, get_twitch_video_by_ids, get_twitch_video_id, parse_time
from app.youtube_api import get_youtube_thumbnail_url, get_youtube_video_id, get_videos
from urllib.parse import urlparse, urlunparse
import asyncio
import logging
import signal
import time
from datetime import datetime
from twitchAPI.type import AuthScope, ChatEvent
from twitchAPI.chat import Chat, EventData, ChatMessage, ChatSub
import re
from typing import TypedDict

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

engine = create_engine(config.database_uri)
SessionLocal = sessionmaker(bind=engine)
ScopedSession = scoped_session(SessionLocal)

class ChannelSettingsDict(TypedDict):
    """TypedDict representing channel settings stored in memory"""
    content_queue_enabled: bool
    chat_collection_enabled: bool
    broadcaster_id: int

class ContentDict(TypedDict):
    """TypedDict representing content stored in memory"""
    url: str
    sanitized_url: str
    title: str
    duration: int
    thumbnail_url: str
    channel_name: str
    author: str | None



shutdown_event = asyncio.Event()

def handle_shutdown(signum, frame):
    loop = asyncio.get_running_loop()
    loop.call_soon_threadsafe(shutdown_event.set)
