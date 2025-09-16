from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from app.models.config import config
import asyncio
from typing import TypedDict
from app.redis_client import RedisTaskQueue
from app.logger import logger
import re
from app.models.content_queue_settings import ContentQueueSettings
from app.models.content_queue import Content, ContentQueue, ContentQueueSubmission, ContentQueueSubmissionSource
from app.models.user import Users, UserWeight, ModerationAction
from app.models import Channels
from app.models.enums import AccountSource, ModerationActionType, ModerationScope
from sqlalchemy import select
from app.twitch_api import Twitch
from datetime import datetime, timedelta
from app.platforms.handler import PlatformRegistry, PlatformHandler

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


# URL regex pattern to detect URLs in messages
url_pattern = re.compile(
    r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[\w/\-?=%.#&:;]*')


def get_platform(url: str) -> str | None:
    """Returns the platform name if supported, else None"""
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
            logger.info("Processing clip creation task %s", task.task_id, extra={
                        "broadcaster_id": task.broadcaster_id})

            # Get the Twitch component
            twitch_bot = self.components.get('twitch')
            if not twitch_bot or not twitch_bot.twitch:
                logger.error(
                    "Twitch component not registered or not initialized")
                return None

            # Create the clip using the Twitch component's client
            clip = await create_clip(task.broadcaster_id, twitch_bot.twitch)

            logger.info("Clip created successfully: %s - %s", clip.id,
                        clip.edit_url, extra={"broadcaster_id": task.broadcaster_id})
            return clip
        except Exception as e:
            logger.error("Error creating clip: %s", e, extra={
                         "broadcaster_id": task.broadcaster_id})
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
            task = ClipCreationTask(
                broadcaster_id=broadcaster_id, task_id=task_id)
            self.redis_queue.enqueue_clip_creation(task)
            logger.info("Enqueued clip creation task %s from bot component",
                        task.task_id, extra={"broadcaster_id": broadcaster_id})
            return task
        except Exception as e:
            logger.error("Error enqueueing clip creation task: %s",
                         e, extra={"broadcaster_id": broadcaster_id})
            return None


def _validate_platform_allowed(url: str, broadcaster_id: int, platform_handler: PlatformHandler, session) -> bool:
    """Validate if the URL platform is supported and allowed for this broadcaster."""
    platform = platform_handler.handler_name

    # Check if platform is allowed for this broadcaster's queue
    queue_settings = session.execute(
        select(ContentQueueSettings).filter(
            ContentQueueSettings.broadcaster_id == broadcaster_id
        )
    ).scalars().one_or_none()

    # If we have queue settings and the platform is not allowed, return early
    if queue_settings and not queue_settings.is_platform_allowed(platform):
        logger.warning("Platform %s is not allowed for this queue",
                       platform, extra={"broadcaster_id": broadcaster_id})
        return False

    return True


async def _get_or_create_content(url: str, broadcaster_id: int, session: scoped_session, platform_handler: PlatformHandler, twitch_client: Twitch | None = None) -> int:
    """Get existing content or create new content from URL."""
    # Check if content already exists
    platform_handler = PlatformRegistry.get_handler_by_url(url)
    existing_content = session.execute(
        select(Content).filter(Content.stripped_url ==
                               platform_handler.deduplicate_url())
    ).scalars().one_or_none()

    if existing_content is None or existing_content.created_at is None:
        logger.info("Content not found in database, fetching data from platform and trying to create it", extra={
                    "broadcaster_id": broadcaster_id})
        # Use platform registry to get the appropriate handler

        # For Twitch platforms, we need a Twitch client
        if platform_handler.platform_name == 'twitch':
            # Get the Twitch client from the TwitchBot if not provided
            if twitch_client is None:
                # Get the Twitch client from the task manager
                twitch_bot = task_manager.components.get('twitch')
                if not twitch_bot or not twitch_bot.twitch:
                    logger.error(
                        "Twitch component not registered or not initialized")
                    raise ValueError("No Twitch client available")
                twitch_client = twitch_bot.twitch

            if twitch_client is None:
                logger.error(
                    "No Twitch client available for fetching video data")
                raise ValueError("No Twitch client available")

            platform_video_data = await platform_handler.fetch_data(twitch=twitch_client)
        else:
            # For YouTube platforms
            platform_video_data = await platform_handler.fetch_data()

        logger.info("Fetched data for url: %s", url, extra={
                    "broadcaster_id": broadcaster_id})

        if existing_content is None:
            # Create new content entry
            content = Content(
                url=url,
                stripped_url=platform_video_data['deduplicated_url'],
                title=platform_video_data['title'],
                duration=platform_video_data['duration'],
                thumbnail_url=platform_video_data['thumbnail_url'],
                channel_name=platform_video_data['channel_name'],
                author=platform_video_data['author'],
                created_at=platform_video_data['created_at']
            )
            session.add(content)
        else:
            existing_content.created_at = platform_video_data['created_at']
            
        session.commit()
        logger.info("Created new content: %s", content, extra={
                    "broadcaster_id": broadcaster_id, "content_id": content.id})
        return content.id
    else:
        logger.info("Content already exists in database", extra={
                    "broadcaster_id": broadcaster_id, "content_id": existing_content.id})
        return existing_content.id

def _timeout_user(user_id: str, duration_seconds: int, channel_id: int, session: scoped_session, reason: str = "Automated moderation", username: str = "Unknown"):
    """Handle user timeout or ban based on duration. If duration is 0, it's a ban, otherwise it's a timeout."""
    # Get or create user - need to provide the required parameters for the existing function
    user = _get_or_create_user(
        external_user_id=user_id, 
        username=username, 
        submission_source_type=ContentQueueSubmissionSource.Twitch, 
        broadcaster_id=channel_id, 
        session=session
    )
    
    # Determine action type based on duration
    if duration_seconds == 0:
        # Permanent ban
        action_type = ModerationActionType.ban
        scope = ModerationScope.channel
        expires_at = None
    else:
        # Timeout
        action_type = ModerationActionType.timeout
        scope = ModerationScope.channel
        expires_at = datetime.now() + timedelta(seconds=duration_seconds)
    
    logger.info("_timeout_user: %s", channel_id)
    channel = session.execute(
        select(Channels).filter(
            Channels.platform_channel_id == str(channel_id)
        )
    ).scalars().one()

    # Create moderation action record
    action = ModerationAction(
        target_user_id=user.id,
        action_type=action_type.value,
        scope=scope.value,
        channel_id=channel.id,  # Using broadcaster_id as channel_id for bot context
        reason=reason,
        duration_seconds=duration_seconds if duration_seconds > 0 else None,
        expires_at=expires_at,
        issued_by=None  # Bot-issued action
    )
    
    session.add(action)
    
    # Clean up content queue entries for this user
    _cleanup_user_content_queue_entries(user.id, channel.id, action_type, duration_seconds, session)
    
    session.commit()
    
    action_desc = "banned" if duration_seconds == 0 else f"timed out for {duration_seconds}s"
    logger.info(f"User {user_id} ({username}) {action_desc} in channel {channel.id}: {reason}")
    
    return action


def _cleanup_user_content_queue_entries(target_user_id: int, channel_id: int, 
                                       action_type: ModerationActionType, 
                                       duration_seconds: int, session: scoped_session) -> int:
    """Clean up content queue entries for moderated users. Removes all unwatched/unskipped entries for bans and entries from the past X seconds for timeouts. minimum 1 minute"""
    count = 0
    
    logger.info("_cleanup_user_content_queue_entries: %s", channel_id)

    channel = session.execute(
        select(Channels)
        .filter(
            Channels.id == channel_id
        )
    ).scalars().one()

    

    if action_type == ModerationActionType.ban:
        # For bans, remove all unwatched/unskipped entries
        
        entries_to_delete = session.execute(
            select(ContentQueueSubmission)
            .join(ContentQueue, ContentQueueSubmission.content_queue_id == ContentQueue.id)
            .where(
                ContentQueue.broadcaster_id == channel.broadcaster_id,
                ContentQueueSubmission.user_id == target_user_id,
                ContentQueue.watched == False,
                ContentQueue.skipped == False
            )
        ).scalars().all()
        
        for entry in entries_to_delete:
            session.delete(entry)
            count += 1
        
        logger.info(f"Cleaned up {count} content queue entries for banned user {target_user_id}")
        
    elif action_type == ModerationActionType.timeout and duration_seconds > 0:
        # For timeouts, remove entries from the past X seconds, minimum 1 minute
        if duration_seconds < 60:
            duration_seconds = 60

        cutoff_time = datetime.now() - timedelta(seconds=duration_seconds)
        
        entries_to_delete = session.execute(
            select(ContentQueueSubmission)
            .join(ContentQueue, ContentQueueSubmission.content_queue_id == ContentQueue.id)
            .where(
                ContentQueue.broadcaster_id == channel.broadcaster_id,
                ContentQueueSubmission.user_id == target_user_id,
                ContentQueue.watched == False,
                ContentQueue.skipped == False,
                ContentQueueSubmission.submitted_at >= cutoff_time
            )
        ).scalars().all()
        
        for entry in entries_to_delete:
            session.delete(entry)
            count += 1
        
        logger.info(f"Cleaned up {count} content queue entries for timed out user {target_user_id} (past {duration_seconds}s)")
        
    session.flush()
    # Clean up ContentQueue entries that are empty
    content_queue_entries_to_hide = session.execute(
        select(ContentQueue)
        .where(
            ContentQueue.broadcaster_id == channel.broadcaster_id,
            ContentQueue.watched == False,
            ContentQueue.skipped == False,
            ContentQueue.disabled == False,
            )
        ).scalars().all()
        
    for queue_entry in content_queue_entries_to_hide:
        if len(queue_entry.submissions) == 0:
            queue_entry.disabled = True
    
    session.flush()
    
    return count


def _get_or_create_user(external_user_id: str, username: str, submission_source_type: ContentQueueSubmissionSource, broadcaster_id: int, session: scoped_session) -> Users:
    """Get existing external user or create new one."""
    account_source: AccountSource = AccountSource.Twitch if submission_source_type == ContentQueueSubmissionSource.Twitch else AccountSource.Discord

    # Find existing user
    user = session.execute(
        select(Users).filter(
            Users.external_account_id == external_user_id,
            Users.account_type == account_source,
        )
    ).scalars().one_or_none()

    if user is None:
        try:
            # Create new user
            user = Users(
                name=username,
                external_account_id=external_user_id,
                account_type=account_source,
                disabled=False
            )
            session.add(user)
            session.flush()  # Flush to get the user ID
            logger.debug("Created user: %s", user,
                         extra={"broadcaster_id": broadcaster_id})
        except Exception as e:
            session.rollback()
            # Check if this was a race condition and the user now exists
            user = session.execute(
                select(Users).filter(
                    Users.external_account_id == external_user_id,
                    Users.account_type == account_source,
                )
            ).scalars().one_or_none()

            if user is not None:
                logger.info("Race condition detected - user was created by another process",
                            extra={"broadcaster_id": broadcaster_id, "user_id": user.id})
            else:
                # Different error, re-raise
                logger.error("Failed to create user: %s",
                             e, extra={"broadcaster_id": broadcaster_id})
                raise

    return user


def _get_or_create_user_weight(user: Users, broadcaster_id: int, session: scoped_session) -> UserWeight:
    """Get existing user weight or create new one."""
    user_weight = session.execute(
        select(UserWeight).filter(
            UserWeight.user_id == user.id,
            UserWeight.broadcaster_id == broadcaster_id,
        )
    ).scalars().one_or_none()

    if user_weight is None:
        try:
            # Create new user weight
            user_weight = UserWeight(
                user_id=user.id,
                broadcaster_id=broadcaster_id,
                weight=1.0,
            )
            session.add(user_weight)
            session.flush()  # Flush to get the weight ID
            logger.debug("Created user weight: %s", user_weight, extra={
                         "broadcaster_id": broadcaster_id})
        except Exception as e:
            session.rollback()
            # Check if this was a race condition and the weight now exists
            user_weight = session.execute(
                select(UserWeight).filter(
                    UserWeight.user_id == user.id,
                    UserWeight.broadcaster_id == broadcaster_id,
                )
            ).scalars().one_or_none()

            if user_weight is not None:
                logger.info("Race condition detected - user weight was created by another process",
                            extra={"broadcaster_id": broadcaster_id, "user_weight_id": user_weight.id})
            else:
                # Different error, re-raise
                logger.error("Failed to create user weight: %s", e, extra={
                             "broadcaster_id": broadcaster_id})
                raise

    return user_weight


def _create_or_update_submission(queue_item_id: int, content_id: int, user: Users, submission_source_type: ContentQueueSubmissionSource, submission_source_id: int, submission_source_ref: str | None, submission_weight: float, user_weight: UserWeight, user_comment: str | None, session: scoped_session) -> ContentQueueSubmission:
    """Create new submission or update existing one."""
    # Check if submission already exists
    existing_submission = session.execute(
        select(ContentQueueSubmission).filter(
            ContentQueueSubmission.content_queue_id == queue_item_id,
            ContentQueueSubmission.user_id == user.id,
            ContentQueueSubmission.submission_source_type == submission_source_type,
            ContentQueueSubmission.submission_source_id == submission_source_id,
        )
    ).scalars().one_or_none()

    if existing_submission is None:
        # Create submission record
        submission = ContentQueueSubmission(
            content_queue_id=queue_item_id,
            content_id=content_id,
            user_id=user.id,
            submitted_at=datetime.now(),
            submission_source_type=submission_source_type,
            submission_source_id=submission_source_id,
            submission_source_ref=submission_source_ref,
            weight=submission_weight * user_weight.weight,
            user_comment=user_comment
        )
        session.add(submission)
        session.flush()
        return submission
    else:
        return existing_submission


def _get_or_create_content_queue_item(broadcaster_id: int, content_id: int, session: scoped_session, platform_handler: PlatformHandler) -> int:
    """Create new ContentQueue item or re-enable existing disabled item."""
    existing_queue_item = session.execute(
        select(ContentQueue).filter(
            ContentQueue.broadcaster_id == broadcaster_id,
            ContentQueue.content_id == content_id,
        )
    ).scalars().one_or_none()

    if existing_queue_item is None:
        queue_item = ContentQueue(
            broadcaster_id=broadcaster_id,
            content_id=content_id,
            content_timestamp=platform_handler.seconds_offset,
        )
        session.add(queue_item)
        session.flush()  # Flush to get the queue item ID
        logger.debug("Added new content to content queue", extra={
                     "broadcaster_id": broadcaster_id, "queue_item_id": queue_item.id})
        return queue_item.id
    else:
        # If the existing item is disabled, re-enable it when someone submits it again
        if existing_queue_item.disabled:
            existing_queue_item.disabled = False
            session.flush()
            logger.info("Re-enabled disabled content queue item", extra={
                       "broadcaster_id": broadcaster_id, "queue_item_id": existing_queue_item.id})
        return existing_queue_item.id


async def add_to_content_queue(url: str, broadcaster_id: int, username: str, external_user_id: str, submission_source_type: ContentQueueSubmissionSource, submission_source_id: int, session: scoped_session, submission_source_ref: str | None = None, user_comment: str | None = None, submission_weight: float = 1.0, twitch_client: Twitch | None = None) -> int | None:
    """Add a URL to the content queue for a channel and record who submitted it"""
    # Create a session if one wasn't provided


    try:
        platform_handler = PlatformRegistry.get_handler_by_url(url)
        # Validate platform and check if allowed

        if not _validate_platform_allowed(url, broadcaster_id, platform_handler, session):
            return None

        # Get or create content
        content_id = await _get_or_create_content(url, broadcaster_id, session, platform_handler, twitch_client)

        # Get or create user and weight
        user = _get_or_create_user(
            external_user_id, username, submission_source_type, broadcaster_id, session)
        user_weight = _get_or_create_user_weight(
            user, broadcaster_id, session)

        if user_weight.banned:
            logger.info("User %s is banned, not adding to content queue",
                        user.name, extra={"broadcaster_id": broadcaster_id})
            return None

        try:
            # Add to content queue
            queue_item_id = _get_or_create_content_queue_item(
                broadcaster_id, content_id, session, platform_handler)

            # Create or update submission
            _create_or_update_submission(queue_item_id, content_id, user, submission_source_type,
                                                      submission_source_id, submission_source_ref, submission_weight, user_weight, user_comment, session)

            # Commit all changes
            session.commit()

            return queue_item_id

        except Exception as e:
            session.rollback()
            # Different error, re-raise
            logger.error("Failed to create content queue item: %s",
                         e, extra={"broadcaster_id": broadcaster_id})
            raise

    except Exception as e:
        session.rollback()
        logger.error("Error adding URL to content queue: %s", e,
                     extra={"broadcaster_id": broadcaster_id})
        return None


async def update_submission_weight(submission_source_id: int, weight: float, session: scoped_session):
    logger.debug("Updating submission weight", extra={
                 "submission_source_id": submission_source_id})
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
        logger.debug("Submission weight updated, new weight: %s", existing_submission.weight, extra={
                     "submission_id": existing_submission.id})
    except Exception as e:
        session.rollback()
        logger.error("Error updating submission weight: %s", e, extra={
                     "submission_source_id": submission_source_id})

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
