import asyncio
from .twitch import main as twitch_main
from .discord import bot as discord_bot
from app.models.config import config

async def main():
    await asyncio.gather(
        discord_bot.start(config.discord_bot_token), # todo: shut down bot cleanly
        twitch_main()
    )

if __name__ == "__main__":
    asyncio.run(main())