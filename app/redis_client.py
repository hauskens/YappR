"""
Redis client for bot tasks
"""
import logging
import uuid
import redis
from typing import Optional
from .models.bot_tasks import ClipCreationTask
from .models.config import config

logger = logging.getLogger("custom_logger")

class RedisTaskQueue:
    """Redis-based task queue manager"""
    
    def __init__(self, redis_uri: Optional[str] = None):
        """Initialize Redis client"""
        self.redis_uri = redis_uri or config.redis_uri
        self.redis_client = None
        self.clip_queue_key = "tasks:clip_creation"
    
    def init(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = redis.from_url(self.redis_uri)
            logger.info(f"Connected to Redis at {self.redis_uri}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.redis_client = None
    
    def enqueue_clip_creation(self, broadcaster_id: str) -> Optional[str]:
        """
        Add a clip creation task to the queue
        
        Args:
            broadcaster_id: Twitch broadcaster ID
            
        Returns:
            task_id: Unique ID for the task, or None if failed
        """
        if not self.redis_client:
            logger.error("Redis client not initialized")
            return None
        
        try:
            task_id = str(uuid.uuid4())
            task = ClipCreationTask(broadcaster_id=broadcaster_id, task_id=task_id)
            
            # Push task to the queue
            self.redis_client.lpush(self.clip_queue_key, task.to_json())
            logger.info(f"Enqueued clip creation task {task_id} for broadcaster {broadcaster_id}")
            return task_id
        except Exception as e:
            logger.error(f"Failed to enqueue clip creation task: {e}")
            return None
    
    def dequeue_clip_creation(self, timeout: int = 0) -> Optional[ClipCreationTask]:
        """
        Get the next clip creation task from the queue
        
        Args:
            timeout: Time to wait for a task in seconds (0 = no blocking)
            
        Returns:
            task: ClipCreationTask or None if no task available
        """
        if not self.redis_client:
            logger.error("Redis client not initialized")
            return None
        
        try:
            # Pop task from the queue (BRPOP blocks until a task is available)
            result = self.redis_client.brpop(self.clip_queue_key, timeout=timeout)
            
            if result:
                _, task_json = result
                task = ClipCreationTask.from_json(task_json)
                logger.info(f"Dequeued clip creation task {task.task_id}")
                return task
            return None
        except Exception as e:
            logger.error(f"Failed to dequeue clip creation task: {e}")
            return None
