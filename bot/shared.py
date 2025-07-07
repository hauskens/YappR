from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from app.models.config import config
import asyncio
from typing import TypedDict
from app.redis_client import RedisTaskQueue
from app.logger import logger
import re
from app.models.db import OAuth, Channels, ChannelSettings, ContentQueueSettings, Content, ContentQueue, ContentQueueSubmission, BroadcasterSettings, ExternalUser, ExternalUserWeight, AccountSource, ContentQueueSubmissionSource
from sqlalchemy import select
from app.twitch_api import Twitch
from datetime import datetime
from bot.platform_handlers import PlatformRegistry, ContentDict

engine = create_engine(config.database_uri)
SessionLocal = sessionmaker(bind=engine)
ScopedSession = scoped_session(SessionLocal)

class ChannelSettingsDict(TypedDict):
    """TypedDict representing channel settings stored in memory"""
    content_queue_enabled: bool
    chat_collection_enabled: bool
    broadcaster_id: int




shutdown_event = asyncio.Event()

def handle_shutdown(signum, frame):
    loop = asyncio.get_running_loop()
    loop.call_soon_threadsafe(shutdown_event.set)

# # Supported platforms and their domain patterns
# supported_platforms = {
#     'youtube': re.compile(r'^https?://(?:www\.)?(youtube\.com/watch\?v=|youtu\.be/)[\w\-]{11}'),
#     'youtube_short': re.compile(r'^https?://(?:www\.)?(youtube\.com/shorts/)[\w\-]{11}'),
#     'youtube_clip': re.compile(r'^https?://(?:www\.)?(youtube\.com/clip/)[\w\-]{36}'),
#     'twitch_video': re.compile(r'^https?://(?:www\.)?twitch\.tv/videos/\d+\?t=\d+h\d+m\d+s'),
#     'twitch_clip': re.compile(r'^https?://(?:clips\.twitch\.tv/[\w\-]+|(?:www\.)?twitch\.tv/\w+/clip/[\w\-]+)'),
# }

# URL regex pattern to detect URLs in messages
url_pattern = re.compile(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[\w/\-?=%.#&:;]*')


def get_platform(url: str) -> str | None:
    """Returns the platform name if supported, else None"""
    # First check with legacy patterns for backward compatibility
    # for platform, pattern in supported_platforms.items():
    #     if pattern.match(url):
    #         return platform
            
    # If not found in legacy patterns, try with PlatformRegistry
    try:
        return PlatformRegistry.get_platform_name(url)
    except (ImportError, ValueError):
        return None

class BotTaskManager:
    """Manages bidirectional task communication between Redis and bot components.
    
    This class handles both incoming tasks from Redis to be processed by bot components
    (Twitch, Discord, etc.) and outgoing tasks from bot components to be sent to Redis.
    
    It's designed to be started at bot startup and run as a background task.
    """
    
    def __init__(self):
        """Initialize the task manager"""
        
        self.redis_queue = RedisTaskQueue()
        self.running = False
        self.poll_interval = 1  # seconds
        
        # Registered bot components that can process tasks
        self.components = {}
        
        # Task handlers for different task types
        self.task_handlers = {
            'create_clip': self._handle_clip_creation
        }
    
    def init(self):
        """Initialize the Redis connection"""
        self.redis_queue.init()
        logger.info("Bot task manager initialized")
    
    def register_component(self, name, component):
        """Register a bot component that can process tasks
        
        Args:
            name: Name of the component (e.g., 'twitch', 'discord')
            component: The component instance
        """
        self.components[name] = component
        logger.info(f"Registered component: {name}")
    
    async def _handle_clip_creation(self, task):
        """Handle a clip creation task
        
        Args:
            task: The clip creation task
            
        Returns:
            The result of the clip creation
        """
        from app.twitch_api import create_clip
        
        try:
            logger.info("Processing clip creation task %s", task.task_id, extra={"broadcaster_id": task.broadcaster_id})
            
            # Get the Twitch component
            twitch_bot = self.components.get('twitch')
            if not twitch_bot or not twitch_bot.twitch:
                logger.error("Twitch component not registered or not initialized")
                return None
            
            # Create the clip using the Twitch component's client
            clip = await create_clip(task.broadcaster_id, twitch_bot.twitch)
            
            logger.info("Clip created successfully: %s - %s", clip.id, clip.edit_url, extra={"broadcaster_id": task.broadcaster_id})
            return clip
        except Exception as e:
            logger.error("Error creating clip: %s", e, extra={"broadcaster_id": task.broadcaster_id})
            return None
    
    async def process_task(self, task):
        """Process a task based on its type
        
        Args:
            task: The task to process
            
        Returns:
            The result of processing the task
        """
        # Currently only supporting clip creation tasks
        task_type = "create_clip"  
        
        if task_type in self.task_handlers:
            return await self.task_handlers[task_type](task)
        else:
            logger.error("Unknown task type: %s", task_type)
            return None
    
    async def run(self):
        """Run the task manager loop"""
        self.running = True
        logger.info("Starting bot task manager loop")
        
        while self.running and not shutdown_event.is_set():
            try:
                # Poll for new tasks
                task = self.redis_queue.dequeue_clip_creation(timeout=1)
                
                if task:
                    # Process the task
                    await self.process_task(task)
                else:
                    # No task available, wait before polling again
                    await asyncio.sleep(self.poll_interval)
            
            except Exception as e:
                logger.error("Error in bot task manager loop: %s", e)
                await asyncio.sleep(self.poll_interval)
        
        logger.info("Bot task manager loop stopped")
    
    def stop(self):
        """Stop the task manager loop"""
        self.running = False
        logger.info("Stopping bot task manager")
    
    # Methods for sending tasks from bot components to Redis
    
    def enqueue_clip_creation(self, broadcaster_id, task_id=None):
        """Enqueue a clip creation task from a bot component
        
        Args:
            broadcaster_id: ID of the broadcaster to create a clip for
            task_id: Optional task ID
            
        Returns:
            The enqueued task
        """
        from app.models.bot_tasks import ClipCreationTask
        
        try:
            task = ClipCreationTask(broadcaster_id=broadcaster_id, task_id=task_id)
            self.redis_queue.enqueue_clip_creation(task)
            logger.info("Enqueued clip creation task %s from bot component", task.task_id, extra={"broadcaster_id": broadcaster_id})
            return task
        except Exception as e:
            logger.error("Error enqueueing clip creation task: %s", e, extra={"broadcaster_id": broadcaster_id})
            return None

async def add_to_content_queue(url: str, broadcaster_id: int, username: str, external_user_id: str, submission_source_type: ContentQueueSubmissionSource, submission_source_id: int, user_comment: str | None = None, submission_weight: float = 1.0, twitch_client: Twitch | None = None, session=None) -> None:
    """Add a URL to the content queue for a channel and record who submitted it"""
    # Create a session if one wasn't provided
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True
    try:
        platform = get_platform(url)
        if not platform:
            logger.info("URL is not supported: %s", url, extra={"broadcaster_id": broadcaster_id})
            return
            
        # Check if platform is allowed for this broadcaster's queue
        queue_settings = session.execute(
            select(ContentQueueSettings).filter(
                ContentQueueSettings.broadcaster_id == broadcaster_id
            )
        ).scalars().one_or_none()
        
        # If we have queue settings and the platform is not allowed, return early
        if queue_settings and not queue_settings.is_platform_allowed(platform):
            logger.warning("Platform %s is not allowed for this queue", platform, extra={"broadcaster_id": broadcaster_id})
            return
        # Check if content already exists
        existing_content = session.execute(
            select(Content).filter(Content.url == url)
        ).scalars().one_or_none()

        if existing_content is None:
            logger.info("Content not found in database, fetching data from platform and trying to create it", extra={"broadcaster_id": broadcaster_id})
            # Use platform registry to get the appropriate handler
            platform_handler = PlatformRegistry.get_handler_by_platform(platform)
            
            # For Twitch platforms, we need a Twitch client
            if platform.startswith('twitch'):
                # Get the Twitch client from the TwitchBot if not provided
                if twitch_client is None:
                    # Get the Twitch client from the task manager
                    twitch_bot = task_manager.components.get('twitch')
                    if not twitch_bot or not twitch_bot.twitch:
                        logger.error("Twitch component not registered or not initialized")
                        return None
                    twitch_client = twitch_bot.twitch
                    
                if twitch_client is None:
                    logger.error("No Twitch client available for fetching video data")
                    raise ValueError("No Twitch client available")
                
                platform_video_data = await platform_handler.fetch_data(url, twitch=twitch_client)
            else:
                # For YouTube platforms
                platform_video_data = await platform_handler.fetch_data(url)
            logger.info("Fetched data for url: %s", url, extra={"broadcaster_id": broadcaster_id})
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
            logger.info("Created new content: %s", content, extra={"broadcaster_id": broadcaster_id, "content_id": content.id})
            content_id = content.id
        else:
            logger.info("Content already exists in database", extra={"broadcaster_id": broadcaster_id, "content_id": existing_content.id})
            content_id = existing_content.id
        
        # Check if this content is already in the queue for this channel
        existing_queue_item = session.execute(
            select(ContentQueue).filter(
                ContentQueue.content_id == content_id,
                ContentQueue.broadcaster_id == broadcaster_id,
            )
        ).scalars().one_or_none()
        account_source: AccountSource = AccountSource.Twitch if submission_source_type == ContentQueueSubmissionSource.Twitch else AccountSource.Discord
        # Find or create external user
        external_user = session.execute(
            select(ExternalUser).filter(
                ExternalUser.external_account_id == int(external_user_id),
                ExternalUser.account_type == account_source,
            )
        ).scalars().one_or_none()
        
        if external_user is None:
            # Create new external user
            external_user = ExternalUser(
                username=username,
                external_account_id=int(external_user_id),
                account_type=account_source,
                disabled=False
            )
            session.add(external_user)
            session.flush()  # Flush to get the user ID
            logger.debug("Created external user: %s", external_user, extra={"broadcaster_id": broadcaster_id})
        
        external_user_weight = session.execute(
            select(ExternalUserWeight).filter(
                ExternalUserWeight.external_user_id == external_user.id,
                ExternalUserWeight.broadcaster_id == broadcaster_id,
            )
        ).scalars().one_or_none()
        if external_user_weight is None:
            # Create new external user weight
            external_user_weight = ExternalUserWeight(
                external_user_id=external_user.id,
                broadcaster_id=broadcaster_id,
                weight=1.0,
            )
            session.add(external_user_weight)
            session.flush()  # Flush to get the weight ID
            logger.debug("Created external user weight: %s", external_user_weight, extra={"broadcaster_id": broadcaster_id})

        if external_user_weight.banned:
            logger.info("External user %s is banned, not adding to content queue", external_user.username, extra={"broadcaster_id": broadcaster_id})
            return

        if existing_queue_item is None:
            # Add to content queue
            queue_item = ContentQueue(
                broadcaster_id=broadcaster_id,
                content_id=content_id,
            )
            session.add(queue_item)
            session.flush()  # Flush to get the queue item ID
            logger.debug("Added new content to content queue", extra={"broadcaster_id": broadcaster_id, "queue_item_id": queue_item.id})
            
            # Create submission record
            submission = ContentQueueSubmission(
                content_queue_id=queue_item.id,
                content_id=content_id,
                user_id=external_user.id,
                submitted_at=datetime.now(),
                submission_source_type=submission_source_type,
                submission_source_id=submission_source_id,
                weight=submission_weight * external_user_weight.weight,
                user_comment=user_comment
            )
            session.add(submission)
            
            # Commit all changes
            session.commit()
            logger.info("Added submission id %s to content queue", submission.id, extra={"broadcaster_id": broadcaster_id, "queue_item_id": queue_item.id})
        else:
            logger.info("Content already in content queue, checking if submission already exists", extra={"broadcaster_id": broadcaster_id, "queue_item_id": existing_queue_item.id})
            existing_submission = session.execute(
                select(ContentQueueSubmission).filter(
                    ContentQueueSubmission.content_queue_id == existing_queue_item.id,
                    ContentQueueSubmission.user_id == external_user.id,
                    ContentQueueSubmission.submission_source_type == submission_source_type,
                    ContentQueueSubmission.submission_source_id == submission_source_id,
                )
            ).scalars().one_or_none()
            if existing_submission is None:
                # Create submission record
                submission = ContentQueueSubmission(
                    content_queue_id=existing_queue_item.id,
                    content_id=content_id,
                    user_id=external_user.id,
                    submitted_at=datetime.now(),
                    submission_source_type=submission_source_type,
                    submission_source_id=submission_source_id,
                    weight=submission_weight * external_user_weight.weight,
                    user_comment=user_comment
                )
                session.add(submission)
                session.commit()
                logger.info("Submission added to content queue", extra={"broadcaster_id": broadcaster_id, "queue_item_id": existing_queue_item.id})
            else:
                logger.info("Submission already exists, updating weight", extra={"broadcaster_id": broadcaster_id, "queue_item_id": existing_queue_item.id})
                existing_submission.weight = submission_weight * external_user_weight.weight
                session.commit()
            
    except Exception as e:
        session.rollback()
        logger.error("Error adding URL to content queue: %s", e, extra={"broadcaster_id": broadcaster_id})
    finally:
        if close_session:
            session.close()

async def update_submission_weight(submission_source_id: int, weight: float, session=None):
    logger.debug("Updating submission weight", extra={"submission_source_id": submission_source_id})
    # Create a session if one wasn't provided
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True
    try:
        existing_submission = session.execute(
            select(ContentQueueSubmission).filter(
                ContentQueueSubmission.submission_source_id == submission_source_id,
            )
        ).scalars().one_or_none()
        if existing_submission is None:
            logger.error("Submission not found")
            raise ValueError("Submission not found")
        existing_submission.weight = max(1, 1 + weight)
        session.commit()
        logger.debug("Submission weight updated, new weight: %s", existing_submission.weight, extra={"submission_id": existing_submission.id})
    except Exception as e:
        session.rollback()
        logger.error("Error updating submission weight: %s", e, extra={"submission_source_id": submission_source_id})
    finally:
        if close_session:
            session.close()

# Singleton instance of the task manager
task_manager = BotTaskManager()


async def start_task_manager():
    """Start the task manager as a background task
    
    This should be called during bot startup
    """
    task_manager.init()
    
    try:
        await task_manager.run()
    except Exception as e:
        logger.error("Error in task manager: %s", e)
    finally:
        task_manager.stop()
