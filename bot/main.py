from twitchAPI.twitch import Twitch, AuthScope
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.db import OAuth
from app.models.config import config
import asyncio
import logging
import signal
import asyncio
from twitchAPI.type import AuthScope, ChatEvent
from twitchAPI.chat import Chat, EventData, ChatMessage, ChatSub

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

engine = create_engine(config.database_uri)
SessionLocal = sessionmaker(bind=engine)

class TwitchBot:
    def __init__(self):
        self.twitch = None
        self.lock = asyncio.Lock()

    async def init_bot(self):
        self.twitch = await Twitch(app_id=config.twitch_client_id, app_secret=config.twitch_client_secret)
        self.twitch.user_auth_refresh_callback = self.save_refresh_token

        token_data = await self.load_token_from_db()
        if not token_data:
            raise Exception("No bot OAuth token found in DB")

        await self.twitch.set_user_authentication(
            token=token_data['access_token'],
            refresh_token=token_data['refresh_token'],
            scope=[AuthScope.CHAT_READ, AuthScope.CHAT_EDIT],
        )
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
    async def on_ready(self, ready_event: EventData):
        logger.info('Bot is ready for work, joining channels')
        # join our target channel, if you want to join multiple, either call join for each individually
        # or even better pass a list of channels as the argument
        channels = ["hauskens"]
        await ready_event.chat.join_room(channels)
        # you can do other bot initialization things in here


    # this will be called whenever a message in a channel was send by either the bot OR another user
    async def on_message(self, msg: ChatMessage):
        logger.info(f'in {msg.room.name}, {msg.user.name} said: {msg.text} - {msg.sent_timestamp}')


    # this will be called whenever someone subscribes to a channel
    async def on_sub(self, sub: ChatSub):
        logger.info(f'New subscription in {sub.room.name}:\n'
            f'  Type: {sub.sub_plan}\n'
            f'  Message: {sub.sub_message}')

    async def on_joined(self, joined_event: EventData):
        logger.info(f'Joined channel {joined_event.room_name}')

shutdown_event = asyncio.Event()

def handle_shutdown(*_):
    shutdown_event.set()

async def main():
    print("✅ Entered main()")
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
    chat.stop()


if __name__ == "__main__":
    logging.info("Starting bot...")
    asyncio.run(main())