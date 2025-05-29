from twitchAPI.twitch import Twitch, AuthScope
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, scoped_session
from app.models.db import OAuth, Channels, ChannelSettings, Platforms, ChatLog
from app.models.config import config
import asyncio
import logging
import signal
import time
from datetime import datetime
from twitchAPI.type import AuthScope, ChatEvent
from twitchAPI.chat import Chat, EventData, ChatMessage, ChatSub

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

engine = create_engine(config.database_uri)
SessionLocal = sessionmaker(bind=engine)
ScopedSession = scoped_session(SessionLocal)

class TwitchBot:
    def __init__(self):
        self.twitch = None
        self.lock = asyncio.Lock()
        self.session = None
        self.message_buffer = []
        self.last_commit_time = time.time()
        self.commit_interval = 5  # Commit every 5 seconds
        self.max_buffer_size = 100    # Commit when buffer reaches this size
        self.enabled_channels = {}  # Store channel info: {room_id: channel_id}

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
            scope=[AuthScope.CHAT_READ, AuthScope.CHAT_EDIT],
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
            for channel in channels:
                self.enabled_channels[channel.platform_channel_id] = channel.id
                
            logger.info(f"Stored {len(self.enabled_channels)} enabled channels in memory")
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
                
            # Create a new ChatLog entry
            chat_log = ChatLog(
                channel_id=self.enabled_channels[room_id],
                timestamp=datetime.fromtimestamp(msg.sent_timestamp / 1000),
                username=msg.user.name,
                message=msg.text,
                external_user_account_id=msg.user.id,
                imported=False,
            )
            
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


    # this will be called whenever someone subscribes to a channel
    async def on_sub(self, sub: ChatSub):
        if sub.room is None:
            logger.warning(f"Received subscription from unknown room: {sub}")
            return
        logger.info(f'New subscription in {sub.room.name}:\n'
            f'  Type: {sub.sub_plan}\n'
            f'  Message: {sub.sub_message}')

    async def on_joined(self, joined_event: EventData):
        if joined_event.room_name is None: # type: ignore
            logger.warning(f"Received joined event from unknown room: {joined_event}")
            return
        logger.info(f'Joined channel {joined_event.room_name}') # type: ignore

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

shutdown_event = asyncio.Event()

def handle_shutdown(signum, frame):
    loop = asyncio.get_running_loop()
    loop.call_soon_threadsafe(shutdown_event.set)


async def main():
    logger.info("Starting bot...")

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    bot = TwitchBot()
    await bot.init_bot()

    chat = await Chat(bot.twitch)
    chat.register_event(ChatEvent.READY, bot.on_ready)
    chat.register_event(ChatEvent.JOINED, bot.on_joined)
    chat.register_event(ChatEvent.MESSAGE, bot.on_message)
    chat.register_event(ChatEvent.SUB, bot.on_sub)

    chat.start()

    await shutdown_event.wait()
    logger.info("Shutting down cleanly.")
    await bot.cleanup()
    chat.stop()
    logger.info("Bot stopped, bye!")


if __name__ == "__main__":
    asyncio.run(main())