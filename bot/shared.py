from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from app.models.config import config
import asyncio
from typing import TypedDict
from app.redis_client import RedisTaskQueue
from app.logger import logger

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
            logger.info(f"Processing clip creation task {task.task_id} for broadcaster {task.broadcaster_id}")
            
            # Get the Twitch component
            twitch_bot = self.components.get('twitch')
            if not twitch_bot or not twitch_bot.twitch:
                logger.error("Twitch component not registered or not initialized")
                return None
            
            # Create the clip using the Twitch component's client
            clip = await create_clip(task.broadcaster_id, twitch_bot.twitch)
            
            logger.info(f"Clip created successfully: {clip.id} - {clip.edit_url}")
            return clip
        except Exception as e:
            logger.error(f"Error creating clip: {e}")
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
            logger.warning(f"Unknown task type: {task_type}")
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
                logger.error(f"Error in bot task manager loop: {e}")
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
            logger.info(f"Enqueued clip creation task {task.task_id} from bot component")
            return task
        except Exception as e:
            logger.error(f"Error enqueueing clip creation task: {e}")
            return None


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
        logger.error(f"Error in task manager: {e}")
    finally:
        task_manager.stop()
