from twitchAPI.twitch import Twitch, AuthScope
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy import select
from app.models.db import OAuth, Channels, ChannelSettings, ChatLog, Content, ContentQueue, ContentQueueSubmission, ExternalUser, AccountSource, ContentQueueSubmissionSource
from app.models.config import config
from app.twitch_api import parse_clip_id, get_twitch_clips, get_twitch_video_by_ids, get_twitch_video_id, parse_time
from app.youtube_api import get_youtube_thumbnail_url, get_youtube_video_id, get_videos
from app.routes import get_broadcaster_by_external_id
from urllib.parse import urlparse, urlunparse
import asyncio
import signal
import time
from datetime import datetime
from twitchAPI.type import AuthScope, ChatEvent
from twitchAPI.chat import Chat, EventData, ChatMessage, ChatSub
from .shared import ChannelSettingsDict, ContentDict, ScopedSession, logger, SessionLocal, handle_shutdown, shutdown_event
import re

class TwitchBot:
    def __init__(self):
        self.twitch = None
        self.session = None
        self.message_buffer: list[ChatLog] = []
        self.lock = asyncio.Lock()
        self.commit_interval = 5  # Commit every 5 seconds
        self.max_buffer_size = 100    # Commit when buffer reaches this size
        self.enabled_channels: dict[str, int] = {}  # Store channel info: {room_id: channel_id}
        self.channel_settings: dict[int, ChannelSettingsDict] = {}  # Store channel settings: {channel_id: settings_dict}
        self.last_commit_time = time.time()

        # URL regex pattern to detect URLs in messages
        self.URL_PATTERN = re.compile(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[\w/\-?=%.#&:;]*')

        # Supported platforms and their domain patterns
        self.SUPPORTED_PLATFORMS = {
            'youtube': re.compile(r'^https?://(?:www\.)?(youtube\.com/watch\?v=|youtu\.be/)[\w\-]{11}'),
            'twitch_video': re.compile(r'^https?://(?:www\.)?twitch\.tv/videos/\d+\?t=\d+h\d+m\d+s'),
            'twitch_clip': re.compile(r'^https?://(?:clips\.twitch\.tv/[\w\-]+|(?:www\.)?twitch\.tv/\w+/clip/[\w\-]+)'),
        }

    async def init_bot(self):
        self.twitch = await Twitch(app_id=config.twitch_client_id, app_secret=config.twitch_client_secret)
        self.twitch.user_auth_refresh_callback = self.save_refresh_token
        
        # Initialize the session
        self.session = ScopedSession()
        
        token_data = await self.load_token_from_db()
        if not token_data:
            raise Exception("No bot OAuth token found in DB")

        await self.twitch.set_user_authentication(
            token=token_data['access_token'],
            refresh_token=token_data['refresh_token'],
            scope=[AuthScope.CHAT_READ, AuthScope.CHAT_EDIT, AuthScope.CLIPS_EDIT],
        )
        
        # Start the background commit task
        asyncio.create_task(self.periodic_commit())
        
        logger.info("Bot initialized")

    async def load_token_from_db(self):
        with SessionLocal() as session:
            try:
                oauth = session.query(OAuth).filter_by(provider='twitch_bot').one()
                return {
                    'access_token': oauth.token['access_token'],
                    'refresh_token': oauth.token['refresh_token']
            }
            except NoResultFound:
                return None

    async def save_refresh_token(self, token: str, refresh_token: str):
        async with self.lock:
            with SessionLocal() as session:
                try:
                    oauth = session.query(OAuth).filter_by(provider='twitch_bot').one()
                    oauth.token = {
                        "access_token": token,
                        "refresh_token": refresh_token
                    }
                    session.commit()
                    logger.info("Bot token refreshed and saved.")
                except Exception as e:
                    logger.error(f"Error saving refreshed token: {e}")


    # this will be called when the event READY is triggered, which will be on bot start
    def get_enabled_twitch_channels(self):
        """Get all Twitch channels that have chat collection enabled and store their info"""
        session = SessionLocal()
        try:
            # Get all Twitch channels with chat collection enabled
            query = select(Channels).join(
                ChannelSettings,
                Channels.id == ChannelSettings.channel_id
            ).where(
                ChannelSettings.chat_collection_enabled == True,
            )
            channels = session.execute(query).scalars().all()
            
            # Store channel information in memory for quick lookups
            self.enabled_channels = {}
            self.channel_settings = {}
            
            for channel in channels:
                channel_id = channel.id
                self.enabled_channels[channel.platform_channel_id] = channel_id
                
                # Store channel settings for quick access
                self.channel_settings[channel_id] = ChannelSettingsDict(
                    content_queue_enabled=channel.settings.content_queue_enabled if channel.settings else False,
                    chat_collection_enabled=channel.settings.chat_collection_enabled if channel.settings else False,
                    broadcaster_id=channel.broadcaster_id,
                )
                
            logger.info(f"Stored {len(self.enabled_channels)} enabled channels in memory with settings")
            return [channel.platform_ref for channel in channels]
        finally:
            session.close()

    async def on_ready(self, ready_event: EventData):
        logger.info('Bot is ready for work, checking for enabled channels')
        # Get channels with chat collection enabled
        channels = self.get_enabled_twitch_channels()
        if not channels:
            logger.info('No channels with chat collection enabled found')
            return
        
        logger.info(f'Joining channels: {channels}')
        await ready_event.chat.join_room(channels)

    async def fetch_youtube_data(self, url: str) -> ContentDict:
        """Fetches video data from YouTube"""
        try:
            logger.info(f"Fetching YouTube data for url: {url}")
            thumbnail_url = get_youtube_thumbnail_url(url)
            video_id = get_youtube_video_id(url)
            video_details = get_videos([video_id])
            return ContentDict(
                url=url,
                sanitized_url=self.sanitize_url(url),
                title=video_details[0].snippet.title,
                duration=int(video_details[0].contentDetails.duration.total_seconds()),
                thumbnail_url=thumbnail_url,
                channel_name=video_details[0].snippet.channelTitle,
                author=None
            )
        except Exception as e:
            logger.error(f"Failed to fetch YouTube data for url: {url}, exception: {e}")
            raise ValueError("Failed to fetch YouTube data")

    async def fetch_twitch_video_data(self, url: str) -> ContentDict:
        """Fetches video data from Twitch"""
        try:
            logger.info(f"Fetching Twitch data for url: {url}")
            video_id = get_twitch_video_id(url)
            video_details = await get_twitch_video_by_ids([video_id], api_client=self.twitch)
            video = video_details[0]
            return ContentDict(
                url=url,
                sanitized_url=self.sanitize_url(url),
                title=video.title,
                duration=parse_time(video.duration),
                thumbnail_url=video.thumbnail_url,
                channel_name=video.user_name,
                author=None
            )
        except Exception as e:
            logger.error(f"Failed to fetch Twitch data for url: {url}, exception: {e}")
            raise ValueError("Failed to fetch Twitch data")

    async def fetch_twitch_clip_data(self, url: str) -> ContentDict:
        """Fetches clip data from Twitch"""
        try:
            logger.info(f"Fetching Twitch data for clip url: {url}")
            clip_id = parse_clip_id(url)
            clip_details = await get_twitch_clips([clip_id], api_client=self.twitch)
            clip = clip_details[0]
            return ContentDict(
                url=url,
                sanitized_url=self.sanitize_url(url),
                title=clip.title,
                duration=int(clip.duration),
                thumbnail_url=clip.thumbnail_url,
                channel_name=clip.broadcaster_name,
                author=clip.creator_name
            )
        except Exception as e:
            logger.error(f"Failed to fetch Twitch data for url: {url}, exception: {e}")
            raise ValueError("Failed to fetch Twitch data")
        
    def get_platform(self, url: str) -> str | None:
        """Returns the platform name if supported, else None"""
        for platform, pattern in self.SUPPORTED_PLATFORMS.items():
            if pattern.match(url):
                return platform
        return None

    def sanitize_url(self, url: str) -> str:
        """Remove junk from url"""
        parsed = urlparse(url)
        return urlunparse(parsed._replace(query='', fragment=''))
    
    async def add_to_content_queue(self, url: str, channel_id: int, username: str, external_user_id: str) -> None:
        """Add a URL to the content queue for a channel and record who submitted it"""
        session = SessionLocal()
        try:
            platform = self.get_platform(url)
            if not platform:
                logger.info(f"URL is not supported: {url}, not sure how we got here...")
                return
            # Check if content already exists
            existing_content = session.execute(
                select(Content).filter(Content.url == url)
            ).scalars().one_or_none()


            if existing_content is None:
                if platform == 'youtube':
                    platform_video_data = await self.fetch_youtube_data(url)
                elif platform == 'twitch_video':
                    platform_video_data = await self.fetch_twitch_video_data(url)
                elif platform == 'twitch_clip':
                    platform_video_data = await self.fetch_twitch_clip_data(url)
                else:
                    logger.info(f"URL is not supported: {url}")
                    return
                logger.info(f"Fetched data for url: {url}, data: {platform_video_data}")
                # Create new content entry
                content = Content(
                    url=url, 
                    stripped_url=platform_video_data['sanitized_url'], 
                    title=platform_video_data['title'], 
                    duration=platform_video_data['duration'], 
                    thumbnail_url=platform_video_data['thumbnail_url'], 
                    channel_name=platform_video_data['channel_name'], 
                    author=platform_video_data['author']
                )
                session.add(content)
                session.flush()  # Flush to get the content ID
                content_id = content.id
            else:
                content_id = existing_content.id
            
            # Check if this content is already in the queue for this channel
            existing_queue_item = session.execute(
                select(ContentQueue).filter(
                    ContentQueue.content_id == content_id,
                    ContentQueue.broadcaster_id == self.channel_settings[channel_id]['broadcaster_id']
                )
            ).scalars().one_or_none()
            
            # Find or create external user
            external_user = session.execute(
                select(ExternalUser).filter(
                    ExternalUser.external_account_id == int(external_user_id),
                    ExternalUser.account_type == AccountSource.Twitch
                )
            ).scalars().one_or_none()
            
            if external_user is None:
                # Create new external user
                external_user = ExternalUser(
                    username=username,
                    external_account_id=int(external_user_id),
                    account_type=AccountSource.Twitch,
                    disabled=False
                )
                session.add(external_user)
                session.flush()  # Flush to get the user ID
            
            if existing_queue_item is None:
                # Add to content queue
                queue_item = ContentQueue(
                    broadcaster_id=self.channel_settings[channel_id]['broadcaster_id'],
                    content_id=content_id,
                )
                session.add(queue_item)
                session.flush()  # Flush to get the queue item ID
                
                # Create submission record
                submission = ContentQueueSubmission(
                    content_queue_id=queue_item.id,
                    content_id=content_id,
                    user_id=external_user.id,
                    submitted_at=datetime.now(),
                    submission_source_type=ContentQueueSubmissionSource.Twitch,
                    submission_source_id=int(external_user_id),
                    weight=1.0
                )
                session.add(submission)
                
                # Commit all changes
                session.commit()
                logger.info(f"Added URL to content queue: {url} for channel ID: {channel_id} by user: {username}")
            else:
                logger.info(f"URL already in content queue: {url} for channel ID: {channel_id}")
                
        except Exception as e:
            session.rollback()
            logger.error(f"Error adding URL to content queue: {e}")
        finally:
            session.close()
    
    # this will be called whenever a message in a channel was send by either the bot OR another user
    async def on_message(self, msg: ChatMessage):
        if msg.room is None:
            logger.warning(f"Received message from unknown room: {msg}")
            return
        try:
            room_id = msg.room.room_id
            
            # Look up channel_id from our in-memory dictionary
            if room_id not in self.enabled_channels:
                logger.warning(f"Received message from untracked room id: {room_id} - {msg.room.name}")
                return
            
            channel_id = self.enabled_channels[room_id]
                
            # Create a new ChatLog entry
            chat_log = ChatLog(
                channel_id=channel_id,
                timestamp=datetime.fromtimestamp(msg.sent_timestamp / 1000),
                username=msg.user.name,
                message=msg.text,
                external_user_account_id=msg.user.id,
                imported=False,
            )
            
            # Check for URLs in the message
            urls = self.URL_PATTERN.findall(msg.text)
            
            # Only process URLs if content queue is enabled for this channel
            if urls and channel_id in self.channel_settings and self.channel_settings[channel_id]['content_queue_enabled']:
                for url in urls:
                    if self.get_platform(url):
                        logger.info(f"Found supported URL in message: {url}")
                        await self.add_to_content_queue(
                            url=url, 
                            channel_id=channel_id,
                            username=msg.user.name,
                            external_user_id=msg.user.id
                        )
            elif urls:
                logger.debug(f"Found URLs but content queue is disabled for channel {channel_id}")
            
            # Add to session and buffer
            self.session.add(chat_log)
            self.message_buffer.append(chat_log)
            
            # Flush to the database but don't commit yet
            self.session.flush()
            
            # Check if we should commit based on buffer size
            if len(self.message_buffer) >= self.max_buffer_size:
                await self.commit_messages()
                
            # Log at debug level to avoid excessive logging
            logger.debug(f'Processed chat message from {msg.user.name} in {msg.room.name}')
        except Exception as e:
            logger.error(f'Error processing chat message: {e} - {msg}')
            self.session.rollback()

    async def periodic_commit(self):
        """Periodically commit messages to the database"""
        while True:
            try:
                # Wait for the commit interval
                await asyncio.sleep(self.commit_interval)
                
                # Check if we need to commit based on time
                current_time = time.time()
                if current_time - self.last_commit_time >= self.commit_interval and self.message_buffer:
                    await self.commit_messages()
            except asyncio.CancelledError:
                # Make sure we commit any remaining messages before exiting
                if self.message_buffer:
                    await self.commit_messages()
                break
            except Exception as e:
                logger.error(f"Error in periodic commit: {e}")
    
    async def commit_messages(self):
        """Commit buffered messages to the database"""
        if not self.message_buffer:
            return
        try:
            # Commit the session
            self.session.commit()
            
            # Log the commit
            count = len(self.message_buffer)
            logger.info(f'Committed {count} chat messages to database')
            
            # Clear the buffer and update the last commit time
            self.message_buffer.clear()
            self.last_commit_time = time.time()
        except Exception as e:
            logger.error(f'Error committing messages: {e}')
            self.session.rollback()
    
    async def cleanup(self):
        """Clean up resources before shutdown"""
        # Commit any remaining messages
        if self.message_buffer:
            await self.commit_messages()
            
        # Close the session
        if self.session:
            self.session.close()

async def main():
    logger.info("Starting twitch bot...")

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    bot = TwitchBot()
    await bot.init_bot()

    chat = await Chat(bot.twitch)
    chat.register_event(ChatEvent.READY, bot.on_ready)
    chat.register_event(ChatEvent.MESSAGE, bot.on_message)

    chat.start()

    await shutdown_event.wait()
    logger.info("Shutting down twitch bot cleanly.")
    await bot.cleanup()
    chat.stop()
    logger.info("Twitch bot stopped")