import asyncio
from .twitch import main as twitch_main
from .discord import main as discord_main
from app.models.config import config

async def main():
    
    # Create a list of tasks to run
    tasks = []
    
    # Add discord bot task if enabled
    if config.bot_discord_enabled:
        tasks.append(discord_main())
    
    # Add twitch bot task if enabled
    if config.bot_twitch_enabled:
        tasks.append(twitch_main())
    
    # Run all enabled tasks
    if tasks:
        await asyncio.gather(*tasks)
    else:
        raise ValueError("No bots enabled, use BOT_DISCORD_ENABLED and/or BOT_TWITCH_ENABLED")

if __name__ == "__main__":
    asyncio.run(main())