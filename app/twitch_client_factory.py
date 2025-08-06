"""
Twitch client factory for managing different types of Twitch API clients.
"""
from typing import Optional
from twitchAPI.twitch import Twitch
from app.models.config import config
from app.models import OAuth, Users
from app.auth import user_oauth_scope, bot_oauth_scope
from app.models import db
from app.logger import logger
from app.services import UserService


class TwitchClientFactory:
    """Factory class for creating different types of Twitch API clients."""
    
    _server_client: Optional[Twitch] = None
    _bot_client: Optional[Twitch] = None
    
    @classmethod
    async def get_server_client(cls) -> Twitch:
        """Get server's default Twitch client using app credentials (singleton)."""
        if cls._server_client is None:
            if config.twitch_client_id is None or config.twitch_client_secret is None:
                logger.error("Twitch client id or secret not configured!")
                raise ValueError("Twitch client id or secret not configured!")
            
            logger.debug("Creating server Twitch client (singleton)")
            cls._server_client = await Twitch(config.twitch_client_id, config.twitch_client_secret)
        
        return cls._server_client
    
    @staticmethod
    async def get_user_client(user: Users) -> Twitch:
        """Get user-authenticated Twitch client with user's OAuth token (new instance each time)."""
        oauth = db.session.query(OAuth).filter_by(user_id=user.id, provider='twitch').one_or_none()
        if not oauth:
            logger.error(f"No Twitch OAuth token found for user {user.name}")
            raise ValueError(f"No Twitch OAuth token found for user {user.name}")
        
        logger.info(f"Creating user Twitch client for user {user.name}")
        # Create a new client instance for user authentication
        client = await Twitch(config.twitch_client_id, config.twitch_client_secret)
        
        await client.set_user_authentication(
            token=oauth.token["access_token"],
            refresh_token=oauth.token["refresh_token"],
            scope=user_oauth_scope
        )
        return client
    
    @classmethod
    async def get_bot_client(cls) -> Twitch:
        """Get bot's Twitch client with bot OAuth credentials (singleton)."""
        if cls._bot_client is None:
            oauth = db.session.query(OAuth).filter_by(provider='twitch_bot').one_or_none()
            if not oauth:
                logger.error("No bot OAuth token found")
                raise ValueError("No bot OAuth token found")
            
            logger.debug("Creating bot Twitch client (singleton)")
            cls._bot_client = await Twitch(config.twitch_client_id, config.twitch_client_secret)
            
            await cls._bot_client.set_user_authentication(
                token=oauth.token["access_token"],
                refresh_token=oauth.token["refresh_token"],
                scope=bot_oauth_scope
            )
        
        return cls._bot_client
    
    @classmethod
    async def reset_server_client(cls):
        """Reset the server client singleton (useful for testing or credential changes)."""
        if cls._server_client:
            await cls._server_client.close()
            cls._server_client = None
            logger.debug("Server Twitch client singleton reset")
    
    @classmethod
    async def reset_bot_client(cls):
        """Reset the bot client singleton (useful for testing or token refresh)."""
        if cls._bot_client:
            await cls._bot_client.close()
            cls._bot_client = None
            logger.debug("Bot Twitch client singleton reset")
    
    @classmethod
    async def reset_all_clients(cls):
        """Reset all singleton clients."""
        await cls.reset_server_client()
        await cls.reset_bot_client()
    
    @staticmethod
    async def get_client_for_context(
        client_type: str = "server", 
        user_id: int | None = None
    ) -> Twitch:
        """
        Get appropriate Twitch client based on context.
        
        Args:
            client_type: Type of client ("server", "user", "bot")
            user_id: Required when client_type is "user"
            
        Returns:
            Configured Twitch client
        """
        if client_type == "server":
            return await TwitchClientFactory.get_server_client()
        elif client_type == "user":
            if user_id is None:
                raise ValueError("user_id is required when client_type is 'user'")
            return await TwitchClientFactory.get_user_client(UserService.get_by_id(user_id))
        elif client_type == "bot":
            return await TwitchClientFactory.get_bot_client()
        else:
            raise ValueError(f"Invalid client type: {client_type}. Must be 'server', 'user', or 'bot'")