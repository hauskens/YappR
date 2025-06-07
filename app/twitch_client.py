"""
Twitch API client
"""
import asyncio
from twitchAPI.twitch import Twitch, AuthScope
from .models.config import config
from app.logger import logger

class TwitchApiClient:
    """Twitch API client wrapper"""
    
    def __init__(self):
        """Initialize Twitch API client"""
        self.twitch = None
        self.initialized = False
    
    def init(self):
        """Initialize Twitch API connection"""
        try:
            # Create event loop if not exists
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # Initialize Twitch client
            self.twitch = loop.run_until_complete(self._init_twitch())
            self.initialized = True
            logger.info("Twitch API client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Twitch API client: {e}")
            self.initialized = False
    
    async def _init_twitch(self):
        """Initialize Twitch API client (async)"""
        twitch = await Twitch(config.twitch_client_id, config.twitch_client_secret)
        await twitch.authenticate_app([])
        return twitch
