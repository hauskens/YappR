import discord
from discord import Message, app_commands
from discord.ext import commands
from sqlalchemy import select
from .shared import ScopedSession, logger, url_pattern, add_to_content_queue, get_platform, update_submission_weight
from app.models.db import BroadcasterSettings, ContentQueueSubmissionSource
import re
import asyncio
from typing import Literal
import signal
import typing
from .shared import handle_shutdown, shutdown_event, task_manager, start_task_manager
from logging import DEBUG
from app.models.config import config


class DiscordBot(commands.Bot):
    def __init__(self, prefix: str = "!", *args: typing.Any, **kwargs: typing.Any) -> None:
        # Initialize intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.messages = True
        intents.reactions = True

        if config.bot_discord_admin_guild is None:
            raise ValueError("BOT_DISCORD_ADMIN_GUILD is not set")
        self.admin_guild = discord.Object(id=config.bot_discord_admin_guild)
        
        # Call parent constructor with intents
        super().__init__(
            command_prefix=commands.when_mentioned_or(prefix),
            intents=intents,
            **kwargs
        )
        
        # Runtime options
        self.allow_thread_creation = not config.environment == "development"
        self.allow_send_message = not config.environment == "development"
        self.allow_reaction = not config.environment == "development"

        # Database session
        self.session = ScopedSession()
        
        # Store the IDs of channels to listen to
        self.active_listening_channels = set()
        
        # Thread management
        self.thread_timeout_minutes: Literal[60, 1440, 4320, 10080] = 4320
        self.pending_vote_updates = {}
        self.tracked_messages = set()
        self.thread_to_message = {}
        
        # Use the shared task manager
        self.task_manager = task_manager

    # async def on_error(self, event_method: str, *args: typing.Any, **kwargs: typing.Any) -> None:
    #     logger.error(f"An error occurred in {event_method}.\n{traceback.format_exc()}")

    async def setup_hook(self):
        """Called when the client is done preparing the data received from Discord"""
        # Sync the command tree
        await self.add_cog(VerifyCommand(self))
        await self.add_cog(AdminCommands(self))
    
    async def schedule_vote_update(self, message: Message, delay=2.0):
        """Schedule a debounced vote update for a message"""
        # If there's already a task running for this message, skip
        if message.id in self.pending_vote_updates:
            return

        async def debounced():
            await asyncio.sleep(delay)
            await self.count_votes(message)
            del self.pending_vote_updates[message.id]

        # Schedule the debounced vote count
        task = asyncio.create_task(debounced())
        self.pending_vote_updates[message.id] = task
    
    async def on_ready(self):
        """Handler for when the bot is ready"""
        print(f'We have logged in as {self.user}')
        
        if not self.allow_thread_creation:
            logger.warning("Thread creation is disabled")
        
        if not self.allow_send_message:
            logger.warning("Send message is disabled")
        
        if not self.allow_reaction:
            logger.warning("Reaction is disabled")
        
        query = select(BroadcasterSettings).where(
            BroadcasterSettings.linked_discord_channel_id.isnot(None),
            BroadcasterSettings.linked_discord_channel_verified == True
        )
        broadcaster_settings = self.session.execute(query).scalars().all()
        logger.info(f"Found {len(broadcaster_settings)} verified broadcaster settings with linked Discord channel")
        
        # Join all verified linked Discord channels
        for setting in broadcaster_settings:
            try:
                channel = self.get_channel(setting.linked_discord_channel_id)
                if channel:
                    self.active_listening_channels.add(setting.linked_discord_channel_id)
                    logger.info(f"Joined verified channel: {channel.name} (ID: {channel.id})")
                else:
                    logger.warning(f"Could not find channel with ID: {setting.linked_discord_channel_id}")
            except Exception as e:
                logger.error(f"Failed to join channel {setting.linked_discord_channel_id}: {e}")
    
    
    async def on_message(self, message: Message):
        """Handler for when a message is received"""
        if message.author.bot:
            return

        # Check if message is in an active listening channel
        in_listening_channel = message.channel.id in self.active_listening_channels

        # Or in a thread whose parent is an active listening channel
        in_thread_of_listening_channel = (
            isinstance(message.channel, discord.Thread)
            and message.channel.parent_id in self.active_listening_channels
        )

        if in_listening_channel or in_thread_of_listening_channel:
            logger.info(f"[{message.author.display_name}]: {message.content}")

        # Process URL messages in the listening channel
        if in_listening_channel and re.search(url_pattern, message.content):
            query = select(BroadcasterSettings).where(
                BroadcasterSettings.linked_discord_channel_id == message.channel.id
            )
            broadcaster_setting = self.session.execute(query).scalars().one_or_none()
            if broadcaster_setting is None:
                logger.error(f"No broadcaster setting found for channel {message.channel.id}")
                return
            
            # Check for URLs in the message
            urls = url_pattern.findall(message.content)
            
            # Only process URLs if content queue is enabled for this channel
            if urls:
                for url in urls:
                    if get_platform(url):
                        logger.info("Found URL %s in message %s", url, message.content, 
                                   extra={"channel_id": broadcaster_setting.broadcaster_id})

                        # Extract user's message without the URL or replace URL with <link> based on position
                        user_comment = message.content
                        
                        for found_url in urls:
                            # Check if the URL is at the start, end, or middle of the message
                            start_pos = user_comment.find(found_url)
                            end_pos = start_pos + len(found_url)
                            
                            # If URL is at the start of the message (accounting for possible whitespace)
                            if start_pos <= len(user_comment.strip()) - len(user_comment.strip().lstrip()):
                                user_comment = user_comment.replace(found_url, "", 1)
                            # If URL is at the end of the message (accounting for possible whitespace)
                            elif end_pos >= len(user_comment.rstrip()):
                                user_comment = user_comment.replace(found_url, "", 1)
                            # If URL is in the middle of the message
                            else:
                                user_comment = user_comment.replace(found_url, "<link>", 1)
                        
                        user_comment = user_comment.strip()

                        # Add the URL to the content queue
                        await add_to_content_queue(
                            url=url, 
                            broadcaster_id=broadcaster_setting.broadcaster_id,
                            username=message.author.display_name,
                            external_user_id=str(message.author.id),
                            submission_source_type=ContentQueueSubmissionSource.Discord,
                            submission_source_id=message.id,
                            user_comment=user_comment if user_comment else None
                        )
            
            # Create a thread if enabled
            if broadcaster_setting.linked_discord_threads_enabled:
                try:
                    if self.allow_thread_creation:
                        thread = await message.create_thread(
                            name=f"Clip from {message.author.display_name}",
                            auto_archive_duration=self.thread_timeout_minutes,
                        )
                    logger.info(f"Thread created for message ID {message.id}")
                    self.tracked_messages.add(message.id)
                    self.thread_to_message[thread.id] = message.id
                except Exception as e:
                    logger.error(f"Failed to create thread: {e}")
            else:
                self.tracked_messages.add(message.id)
    
    async def count_votes(self, message: discord.Message):
        """Count unique users who reacted to a message"""
        unique_users = set()
        for reaction in message.reactions:
            async for user in reaction.users():
                if not user.bot and user.id != message.author.id:
                    unique_users.add(user.id)

        logger.info(f"Counted {len(unique_users)} unique users for message ID {message.id}")
        await update_submission_weight(message.id, len(unique_users))
        return len(unique_users)
    
    async def on_raw_reaction_add(self, payload):
        """Handler for when a reaction is added to a message"""
        if payload.user_id == self.user.id:
            return
        if payload.message_id not in self.tracked_messages:
            return

        channel = await self.fetch_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        await self.schedule_vote_update(message)
    
    async def on_raw_reaction_remove(self, payload):
        """Handler for when a reaction is removed from a message"""
        if payload.user_id == self.user.id:
            return
        if payload.message_id not in self.tracked_messages:
            return

        channel = await self.fetch_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        await self.schedule_vote_update(message)
    
    async def cleanup(self):
        """Clean up resources"""
        logger.info("Cleaning up Discord bot resources")
        
        # Close the session
        if self.session:
            self.session.close()
    
    async def start(self, token):
        """Start the Discord bot"""
        await super().start(token)

class VerifyCommand(commands.Cog):
    def __init__(self, bot: DiscordBot):
        self.bot = bot
    @app_commands.command(name="verify", description="Verify a channel for the bot to listen to")
    async def verify_command(self, interaction: discord.Interaction):
        """Verify a channel for the bot to listen to"""
        # Find broadcaster settings with this channel ID
        logger.info(f"Verifying channel {interaction.channel_id}")
        if interaction.channel_id is not None and interaction.channel_id in self.bot.active_listening_channels:
            if self.bot.allow_send_message:
                await interaction.response.send_message(f"✅ This channel is already verified")
                logger.info(f"Channel {interaction.channel_id} is already verified")
            return
        
        query = select(BroadcasterSettings).where(
            BroadcasterSettings.linked_discord_channel_id == interaction.channel_id
        )
        broadcaster_setting = self.bot.session.execute(query).scalars().first()
        
        if broadcaster_setting and interaction.channel_id is not None:
            # Verify the channel
            broadcaster_setting.linked_discord_channel_verified = True
            self.bot.session.commit()
            
            # Add to active listening channels
            self.bot.active_listening_channels.add(interaction.channel_id)
            if self.bot.allow_send_message:
                await interaction.response.send_message(f"✅ Channel verified and now listening to messages in <#{interaction.channel_id}>")
            logger.info(f"Channel {interaction.channel_id} verified and listening started by {interaction.user.name}", 
                    extra={"broadcaster_id": broadcaster_setting.broadcaster_id})
        else:
            # No broadcaster found with this channel ID
            if self.bot.allow_send_message:
                await interaction.response.send_message(
                    f"❌ This discord channel is not linked to a broadcaster. In YappR, go to a broadcaster and add the channel id `{interaction.channel_id}`."
                )
            logger.info(f"Channel {interaction.channel_id} is not linked to a broadcaster")

class AdminCommands(commands.Cog):
    def __init__(self, bot: DiscordBot):
        self.bot = bot
    @app_commands.command(name="test")
    @app_commands.guilds(discord.Object(id=config.bot_discord_admin_guild)) # type: ignore
    async def test(self, interaction: discord.Interaction) -> None:
        logger.info("Test command")
        await interaction.response.send_message("Test command")

    @app_commands.command(name="sync")
    @app_commands.guilds(discord.Object(id=config.bot_discord_admin_guild)) # type: ignore
    async def sync(self, interaction: discord.Interaction) -> None:
        logger.info("Syncing command tree")
        try:
            if config.environment == "development":
                logger.info("Syncing command tree to guild")
                await self.bot.tree.sync(guild=self.bot.admin_guild)
                await interaction.response.send_message(f"{config.environment}: Synced command tree to guild")
            else:
                logger.info("Syncing command tree to all guilds")
                await self.bot.tree.sync()
                await interaction.response.send_message(f"{config.environment}: Synced command tree to all guilds")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")
            await interaction.response.send_message(f"{config.environment}: Failed to sync commands, check logs")

# Create a global instance of the bot
bot = DiscordBot()

async def main():
    """Main entry point for the Discord bot"""
    logger.info("Starting Discord bot...")

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)
    discord.utils.setup_logging(level=DEBUG)
    
    # Initialize the task manager
    task_manager.init()
    
    # Register the bot with the task manager
    task_manager.register_component('discord', bot)

    # Start the task manager in a background task
    task_manager_task = asyncio.create_task(start_task_manager())

    # Start the bot
    try:
        from app.models.config import config
        await bot.start(config.discord_bot_token)
    except Exception as e:
        logger.error(f"Error starting Discord bot: {e}")
    finally:
        # Wait for shutdown signal
        await shutdown_event.wait()
        logger.info("Shutting down Discord bot cleanly.")
        
        # Clean up resources
        await bot.cleanup()
        
        # Cancel the task manager task
        if not task_manager_task.done():
            task_manager_task.cancel()
            try:
                await task_manager_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Discord bot stopped")