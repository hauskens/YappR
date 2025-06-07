from twitchAPI.twitch import Twitch, AuthScope
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy import select
from app.models.db import OAuth, Channels, ChannelSettings, ChatLog, Content, ContentQueue, ContentQueueSubmission, ExternalUser, AccountSource, ContentQueueSubmissionSource
from app.models.config import config
from app.twitch_api import parse_clip_id, get_twitch_clips, get_twitch_video_by_ids, get_twitch_video_id, parse_time
from app.youtube_api import get_youtube_thumbnail_url, get_youtube_video_id, get_videos, get_youtube_video_id_from_clip
from urllib.parse import urlparse, urlunparse
import asyncio
import signal
import time
from datetime import datetime
from twitchAPI.type import AuthScope, ChatEvent
from twitchAPI.chat import Chat, EventData, ChatMessage
from .shared import ChannelSettingsDict, ContentDict, ScopedSession, logger, SessionLocal, handle_shutdown, shutdown_event, task_manager, start_task_manager
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
        self.connected_channels = set()  # Keep track of channels we're already connected to
        self.channel_check_interval = 60  # Check for new channels every 60 seconds
        self.chat = None  # Reference to the chat object

        # URL regex pattern to detect URLs in messages
        self.URL_PATTERN = re.compile(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[\w/\-?=%.#&:;]*')

        # Supported platforms and their domain patterns
        self.SUPPORTED_PLATFORMS = {
            'youtube': re.compile(r'^https?://(?:www\.)?(youtube\.com/watch\?v=|youtu\.be/)[\w\-]{11}'),
            'youtube_short': re.compile(r'^https?://(?:www\.)?(youtube\.com/shorts/)[\w\-]{11}'),
            'youtube_clip': re.compile(r'^https?://(?:www\.)?(youtube\.com/clip/)[\w\-]{36}'),
            'twitch_video': re.compile(r'^https?://(?:www\.)?twitch\.tv/videos/\d+\?t=\d+h\d+m\d+s'),
            'twitch_clip': re.compile(r'^https?://(?:clips\.twitch\.tv/[\w\-]+|(?:www\.)?twitch\.tv/\w+/clip/[\w\-]+)'),
        }
        # Use the shared task manager instead of creating a separate Redis queue
        self.task_manager = task_manager

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
        
        # Start the periodic channel check task
        asyncio.create_task(self.periodic_channel_check())
        
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
                logger.error("No bot OAuth token found in DB")
                raise Exception("No bot OAuth token found in DB")

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
                    logger.error("Error saving refreshed token: %s", str(e))


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
                
            logger.debug("Stored %d enabled channels in memory with settings", len(self.enabled_channels))
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
        
        # Filter out channels we're already connected to
        new_channels = [channel for channel in channels if channel not in self.connected_channels]
        
        if not new_channels:
            logger.info('Already connected to all enabled channels')
            return
            
        logger.info('Joining channels: %s', new_channels)
        await ready_event.chat.join_room(new_channels)
        
        # Update our connected channels set
        self.connected_channels.update(new_channels)
        logger.info('Now connected to %d channels', len(self.connected_channels))

    async def fetch_youtube_clip_data(self, url: str) -> ContentDict:
        """Fetches video data from YouTube clip"""
        try:
            logger.info("Fetching YouTube clip data for url: %s", url)
            video_id = get_youtube_video_id_from_clip(url)
            original_url = f"https://www.youtube.com/watch?v={video_id}"
            thumbnail_url = get_youtube_thumbnail_url(original_url)
            if video_id is None:
                logger.error("Failed to fetch YouTube clip data for url: %s", url)
                raise ValueError("Failed to fetch YouTube clip data")
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
            logger.error("Failed to fetch YouTube clip data for url: %s, exception: %s", url, e)
            raise ValueError("Failed to fetch YouTube clip data")

    async def fetch_youtube_data(self, url: str) -> ContentDict:
        """Fetches video data from YouTube"""
        try:
            logger.info("Fetching YouTube data for url: %s", url)
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
            logger.error("Failed to fetch YouTube data for url: %s, exception: %s", url, e)
            raise ValueError("Failed to fetch YouTube data")

    async def fetch_twitch_video_data(self, url: str) -> ContentDict:
        """Fetches video data from Twitch"""
        try:
            logger.info("Fetching Twitch data for url: %s", url)
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
            logger.error("Failed to fetch Twitch data for url: %s, exception: %s", url, e)
            raise ValueError("Failed to fetch Twitch data")

    async def fetch_twitch_clip_data(self, url: str) -> ContentDict:
        """Fetches clip data from Twitch"""
        try:
            logger.info("Fetching Twitch data for clip url: %s", url)
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
            logger.error("Failed to fetch Twitch data for url: %s, exception: %s", url, e)
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
    
    async def add_to_content_queue(self, url: str, channel_id: int, username: str, external_user_id: str, user_comment: str | None = None) -> None:
        """Add a URL to the content queue for a channel and record who submitted it"""
        session = SessionLocal()
        try:
            platform = self.get_platform(url)
            if not platform:
                logger.info("URL is not supported: %s, not sure how we got here...", url, extra={"channel_id": channel_id})
                return
            # Check if content already exists
            existing_content = session.execute(
                select(Content).filter(Content.url == url)
            ).scalars().one_or_none()


            if existing_content is None:
                logger.info("Content not found in database, fetching data from platform and trying to create it", extra={"channel_id": channel_id})
                if platform == 'youtube':
                    platform_video_data = await self.fetch_youtube_data(url)
                elif platform == 'youtube_short':
                    platform_video_data = await self.fetch_youtube_data(url)
                elif platform == 'youtube_clip':
                    platform_video_data = await self.fetch_youtube_clip_data(url)
                elif platform == 'twitch_video':
                    platform_video_data = await self.fetch_twitch_video_data(url)
                elif platform == 'twitch_clip':
                    platform_video_data = await self.fetch_twitch_clip_data(url)
                else:
                    logger.info("URL is not supported: %s", url, extra={"channel_id": channel_id})
                    return
                logger.info("Fetched data for url: %s", url, extra={"channel_id": channel_id})
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
                logger.info("Created new content: %s", content, extra={"channel_id": channel_id, "content_id": content.id})
                content_id = content.id
            else:
                logger.info("Content already exists in database", extra={"channel_id": channel_id, "content_id": existing_content.id})
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
                logger.debug("Created external user: %s", external_user, extra={"channel_id": channel_id})
            
            if existing_queue_item is None:
                # Add to content queue
                queue_item = ContentQueue(
                    broadcaster_id=self.channel_settings[channel_id]['broadcaster_id'],
                    content_id=content_id,
                )
                session.add(queue_item)
                session.flush()  # Flush to get the queue item ID
                logger.debug("Added new content to content queue", extra={"channel_id": channel_id, "queue_item_id": queue_item.id})
                
                # Create submission record
                submission = ContentQueueSubmission(
                    content_queue_id=queue_item.id,
                    content_id=content_id,
                    user_id=external_user.id,
                    submitted_at=datetime.now(),
                    submission_source_type=ContentQueueSubmissionSource.Twitch,
                    submission_source_id=int(external_user_id),
                    weight=1.0,
                    user_comment=user_comment
                )
                session.add(submission)
                
                # Commit all changes
                session.commit()
                logger.info("Added submission id %s to content queue", submission.id, extra={"channel_id": channel_id, "queue_item_id": queue_item.id})
            else:
                logger.info("Content already in content queue", extra={"channel_id": channel_id, "queue_item_id": queue_item.id})
                
        except Exception as e:
            session.rollback()
            logger.error("Error adding URL to content queue: %s", e, extra={"channel_id": channel_id})
        finally:
            session.close()
    
    # this will be called whenever a message in a channel was send by either the bot OR another user
    async def on_message(self, msg: ChatMessage):
        if msg.room is None:
            logger.warning("Received message from unknown room: %s", msg)
            return
        try:
            room_id = msg.room.room_id
            
            # Look up channel_id from our in-memory dictionary
            if room_id not in self.enabled_channels:
                logger.warning("Received message from untracked room id: %s - %s", room_id, msg.room.name)
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
            if self.channel_settings and self.channel_settings[channel_id]['content_queue_enabled']:

                # Check for URLs in the message
                urls = self.URL_PATTERN.findall(msg.text)
                
                # Only process URLs if content queue is enabled for this channel
                if urls:
                    for url in urls:
                        if self.get_platform(url):
                            logger.info("Found URL %s in message %s", url, msg.text, extra={"channel_id": channel_id})
                            
                            # Extract user's message without the URL or replace URL with <link> based on position
                            user_comment = msg.text
                            
                            for found_url in urls:
                                # Check if the URL is at the start, end, or middle of the message
                                start_pos = user_comment.find(found_url)
                                end_pos = start_pos + len(found_url)
                                
                                # If URL is at the start of the message (accounting for possible whitespace)
                                if start_pos <= len(user_comment.strip()) - len(user_comment.strip().lstrip()):
                                    user_comment = user_comment.replace(found_url, "", 1)
                                # If URL is at the end of the message (accounting for possible whitespace)
                                elif end_pos >= len(user_comment.rstrip()):
                                    user_comment = user_comment.replace(found_url, "", 1)
                                # If URL is in the middle of the message
                                else:
                                    user_comment = user_comment.replace(found_url, "<link>", 1)
                            
                            user_comment = user_comment.strip()
                            
                            await self.add_to_content_queue(
                                url=url, 
                                channel_id=channel_id,
                                username=msg.user.name,
                                external_user_id=msg.user.id,
                                user_comment=user_comment if user_comment else None
                            )
            
            # Add to session and buffer
            self.session.add(chat_log)
            self.message_buffer.append(chat_log)
            
            # Flush to the database but don't commit yet
            self.session.flush()
            
            # Check if we should commit based on buffer size
            if len(self.message_buffer) >= self.max_buffer_size:
                await self.commit_messages()
                
        except Exception as e:
            logger.error("Error processing chat message: %s - %s", e, msg)
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
                logger.error("Error in periodic commit: %s", e)
    
    async def commit_messages(self):
        """Commit buffered messages to the database"""
        if not self.message_buffer:
            return
        try:
            # Commit the session
            self.session.commit()
            
            # Log the commit
            count = len(self.message_buffer)
            logger.info("Committed %s chat messages to database", count)
            
            # Clear the buffer and update the last commit time
            self.message_buffer.clear()
            self.last_commit_time = time.time()
        except Exception as e:
            logger.error("Error committing messages: %s", e)
            self.session.rollback()
    
    async def periodic_channel_check(self):
        """Periodically check for new channels to join and disconnect from channels no longer needed"""
        logger.info("Starting periodic channel check")
        while True:
            try:
                # Wait for the check interval
                await asyncio.sleep(self.channel_check_interval)
                
                # Make sure we have a chat reference
                if not self.chat:
                    logger.error("Chat reference not available")
                    continue
                
                # Get current enabled channels
                channels = self.get_enabled_twitch_channels()
                if not channels:
                    logger.info("No channels with chat collection enabled found")
                    # If we're connected to any channels, we should disconnect from all of them
                    if self.connected_channels:
                        channels_to_leave = list(self.connected_channels)
                        logger.info("Leaving all channels: %s", channels_to_leave)
                        await self.chat.leave_room(channels_to_leave)
                        self.connected_channels.clear()
                    continue
                
                # Find channels to join (new channels)
                new_channels = [channel for channel in channels if channel not in self.connected_channels]
                
                # Find channels to leave (no longer in the enabled list)
                channels_to_leave = [channel for channel in self.connected_channels if channel not in channels]
                
                # Join new channels if any
                if new_channels:
                    logger.info("Joining new channels: %s", new_channels)
                    await self.chat.join_room(new_channels)
                    self.connected_channels.update(new_channels)
                
                # Leave channels that are no longer enabled
                if channels_to_leave:
                    logger.info("Leaving channels: %s", channels_to_leave)
                    await self.chat.leave_room(channels_to_leave)
                    for channel in channels_to_leave:
                        self.connected_channels.remove(channel)
                
                if new_channels or channels_to_leave:
                    logger.info("Now connected to %s channels", len(self.connected_channels))
                else:
                    logger.debug("No changes to channel connections needed")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in periodic channel check: %s", e)
    
    async def cleanup(self):
        """Clean up resources"""
        logger.info("Cleaning up resources")
        
        # Commit any pending changes
        if self.session:
            await self.commit_messages()
            
        # Close the session
        if self.session:
            self.session.close()

async def main():
    logger.info("Starting twitch bot...")

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    # Initialize the bot
    bot = TwitchBot()
    await bot.init_bot()

    # Initialize the task manager
    task_manager.init()
    
    # Register the bot with the task manager
    task_manager.register_component('twitch', bot)

    # Start the chat connection
    chat = await Chat(bot.twitch)
    chat.register_event(ChatEvent.READY, bot.on_ready)
    chat.register_event(ChatEvent.MESSAGE, bot.on_message)
    chat.start()
    
    # Store chat reference in the bot for periodic channel check
    bot.chat = chat
    
    # Start the task manager in a background task
    task_manager_task = asyncio.create_task(start_task_manager())

    # Wait for shutdown signal
    await shutdown_event.wait()
    logger.info("Shutting down twitch bot cleanly.")
    
    # Clean up resources
    await bot.cleanup()
    chat.stop()
    
    # Cancel the task manager task
    if not task_manager_task.done():
        task_manager_task.cancel()
        try:
            await task_manager_task
        except asyncio.CancelledError:
            pass
    
    logger.info("Twitch bot stopped")