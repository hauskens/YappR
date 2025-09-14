import discord
from discord import Message, app_commands
from discord.ext import commands, tasks
from sqlalchemy import select
from sqlalchemy.orm import scoped_session
from .shared import ScopedSession, logger, url_pattern, add_to_content_queue, get_platform, update_submission_weight
from app.models.broadcaster import BroadcasterSettings
from app.models.content_queue import ContentQueueSubmission, ContentQueueSubmissionSource, ContentQueue
import re
import asyncio
import os
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
        self.allow_thread_creation = not config.debug
        self.allow_send_message = not config.debug
        self.allow_reaction = not config.debug
        logger.info(f"Debug mode: {config.debug}")
        logger.info(f"Allow thread creation: {self.allow_thread_creation}")
        logger.info(f"Allow send message: {self.allow_send_message}")
        logger.info(f"Allow reaction: {self.allow_reaction}")
        # Database session
        self.session = ScopedSession()

        # Store the IDs of channels to listen to
        self.active_listening_channels: set[int] = set()

        # Thread management
        self.thread_timeout_minutes: Literal[60, 1440, 4320, 10080] = 4320
        self.pending_vote_messages: set[discord.RawReactionActionEvent] = set()
        self.pending_test: set[str] = set()
        self.tracked_messages: set[int] = set()
        self.thread_to_message: dict[int, int] = {}

        # Use the shared task manager
        self.task_manager = task_manager

    async def setup_hook(self):
        """Called when the client is done preparing the data received from Discord"""
        # Sync the command tree
        await self.add_cog(VerifyCommand(self))
        if os.getenv("BOT_DISCORD_FORCE_SYNC"):
            try:
                logger.warning("Syncing commands forcefully")
                await self.tree.sync()
            except Exception as e:
                logger.error(f"Failed to sync commands: {e}")

    @tasks.loop(seconds=5)
    async def schedule_vote_update(self):
        """Schedule a debounced vote update for a message"""
        await asyncio.sleep(5)
        pending_message = self.pending_vote_messages.pop()
        logger.info("Processing vote update for message %s",
                    pending_message.message_id)
        await self.count_votes(pending_message)

        if len(self.pending_vote_messages) == 0:
            logger.info("No more pending vote updates, stopping loop")
            self.schedule_vote_update.stop()

    def add_pending_vote(self, payload: discord.RawReactionActionEvent):
        if len(self.pending_vote_messages) == 0:
            self.schedule_vote_update.start()
        self.pending_vote_messages.add(payload)

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
        logger.info(
            f"Found {len(broadcaster_settings)} verified broadcaster settings with linked Discord channel")

        # Join all verified linked Discord channels
        for setting in broadcaster_settings:
            try:
                channel = self.get_channel(setting.linked_discord_channel_id)
                if channel:
                    self.active_listening_channels.add(
                        setting.linked_discord_channel_id)
                    logger.info(
                        f"Joined verified channel: {channel.name} (ID: {channel.id})")
                else:
                    logger.warning(
                        f"Could not find channel with ID: {setting.linked_discord_channel_id}")
            except Exception as e:
                logger.error(
                    f"Failed to join channel {setting.linked_discord_channel_id}: {e}")

        # Get all message IDs that are in the content queue but not yet watched or skipped
        tracked_messages_query = select(ContentQueueSubmission.submission_source_id).join(
            ContentQueue,
            ContentQueueSubmission.content_queue_id == ContentQueue.id
        ).where(
            ContentQueueSubmission.submission_source_type == ContentQueueSubmissionSource.Discord,
            ContentQueue.watched == False,
            ContentQueue.skipped == False
        )

        # Execute the query and add the message IDs to tracked_messages
        result = self.session.execute(tracked_messages_query).scalars().all()
        for message_id in result:
            logger.info(f"Tracking message ID: {message_id}")
            self.tracked_messages.add(message_id)
        logger.info(
            f"Tracking {len(self.tracked_messages)} messages for vote updates")

    async def on_message_delete(self, message: Message):
        if message.id in self.tracked_messages:
            self.tracked_messages.remove(message.id)
            logger.info(f"Removed message ID {message.id} from tracked messages")
            submission = self.session.execute(select(ContentQueueSubmission).where(
                ContentQueueSubmission.submission_source_id == message.id,
                ContentQueueSubmission.submission_source_type == ContentQueueSubmissionSource.Discord
            )).scalars().one_or_none()
            logger.info(f"Found submission: {submission}")
            if submission:
                content_queue = self.session.execute(select(ContentQueue).where(
                    ContentQueue.id == submission.content_queue_id
                )).scalars().one()
                self.session.delete(submission)
                self.session.flush()
                logger.info(f"Deleted submission: {submission} has {len(content_queue.submissions)} submissions")
                #clean up content queue items that are linked to this submission if they are not watched or skipped or empty
                if len(content_queue.submissions) == 0:
                    logger.info(f"Disabling entry: {content_queue}")
                    content_queue.disabled = True
                self.session.commit()

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
            logger.debug(f"Looking for broadcaster setting with channel ID: {message.channel.id} (type: {type(message.channel.id)})")
            query = select(BroadcasterSettings).where(
                BroadcasterSettings.linked_discord_channel_id == message.channel.id
            )
            broadcaster_setting = self.session.execute(
                query).scalars().one_or_none()
            if broadcaster_setting is None:
                # Query all broadcaster settings to see what channel IDs exist
                all_settings = self.session.execute(
                    select(BroadcasterSettings).where(
                        BroadcasterSettings.linked_discord_channel_id.isnot(None)
                    )
                ).scalars().all()
                logger.error(
                    f"No broadcaster setting found for channel {message.channel.id}. "
                    f"Available channel IDs: {[s.linked_discord_channel_id for s in all_settings]}")
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
                                user_comment = user_comment.replace(
                                    found_url, "", 1)
                            # If URL is at the end of the message (accounting for possible whitespace)
                            elif end_pos >= len(user_comment.rstrip()):
                                user_comment = user_comment.replace(
                                    found_url, "", 1)
                            # If URL is in the middle of the message
                            else:
                                user_comment = user_comment.replace(
                                    found_url, "<link>", 1)

                        user_comment = user_comment.strip()

                        # Add the URL to the content queue
                        await add_to_content_queue(
                            url=url,
                            broadcaster_id=broadcaster_setting.broadcaster_id,
                            username=message.author.display_name,
                            external_user_id=str(message.author.id),
                            submission_source_type=ContentQueueSubmissionSource.Discord,
                            submission_source_id=message.id,
                            user_comment=user_comment if user_comment else None,
                            session=self.session
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

    async def count_votes(self, payload: discord.RawReactionActionEvent):
        """Count unique users who reacted to a message"""
        unique_users = set()
        logger.info(f"Counting votes for message ID {payload.message_id}")
        try:
            channel = self.get_channel(payload.channel_id)
            if channel is None:
                channel = await self.fetch_channel(payload.channel_id)

            if channel is None:
                logger.error(f"Could not find channel {payload.channel_id}")
                return

            # Handle different channel types
            if isinstance(channel, (discord.TextChannel, discord.Thread)):
                # These channel types support fetch_message
                message = await channel.fetch_message(payload.message_id)
                for reaction in message.reactions:
                    async for user in reaction.users():
                        if not user.bot and user.id != message.author.id:
                            unique_users.add(user.id)
                logger.debug(
                    f"Counted {len(unique_users)} unique users for message ID {message.id}")
                await update_submission_weight(payload.message_id, len(unique_users), session=self.session)
            else:
                logger.error(
                    f"Channel type {type(channel).__name__} does not support fetch_message")
                return
        except Exception as e:
            logger.error(f"Failed to count votes: {e}")

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Handler for when a reaction is added to a message"""
        if payload.message_id not in self.tracked_messages:
            return
        await self.add_pending_vote(payload)

    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        """Handler for when a reaction is removed from a message"""
        if payload.message_id not in self.tracked_messages:
            return

        await self.add_pending_vote(payload)

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
        await interaction.response.defer(ephemeral=True, thinking=True)
        # Find broadcaster settings with this channel ID
        logger.info(f"Verifying channel {interaction.channel_id}")
        try:
            query = select(BroadcasterSettings).where(
                BroadcasterSettings.linked_discord_channel_id == interaction.channel_id
            )
            broadcaster_setting = self.bot.session.execute(
                query).scalars().one_or_none()

            if interaction.channel_id is not None and interaction.channel_id in self.bot.active_listening_channels and broadcaster_setting is not None:
                if broadcaster_setting.linked_discord_channel_verified:
                    logger.info(f"Channel {interaction.channel_id} is already verified", extra={
                                "discord_channel_id": interaction.channel_id})
                    if self.bot.allow_send_message:
                        await interaction.followup.send(f"✅ This channel is already verified")
                    return
            elif interaction.channel_id is not None and broadcaster_setting is not None:
                # Verify the channel
                broadcaster_setting.linked_discord_channel_verified = True
                self.bot.session.commit()

                # Add to active listening channels
                self.bot.active_listening_channels.add(interaction.channel_id)
                if self.bot.allow_send_message:
                    await interaction.followup.send(f"✅ Channel verified and now listening to messages in <#{interaction.channel_id}>, clips posted here will be added to the content queue.")
                    return
                logger.info("Channel is verified",
                            extra={"broadcaster_id": broadcaster_setting.broadcaster_id, "discord_channel_id": interaction.channel_id})
                return
            else:
                # No broadcaster found with this channel ID
                if self.bot.allow_send_message:
                    await interaction.followup.send(
                        f"❌ This discord channel is not linked to a broadcaster. In YappR, go to a Broadcaster > Broadcast Settings > Linked Discord Channel and add the channel id: `{interaction.channel_id}`."
                    )
                logger.info("Channel is not linked to a broadcaster", extra={
                            "discord_channel_id": interaction.channel_id})
                return
        except Exception as e:
            logger.error(f"Failed to verify channel: {e}")
            if self.bot.allow_send_message:
                await interaction.followup.send(f"❌ Failed to verify channel: {e}")
            return

    @app_commands.command(name="test")
    # type: ignore
    @app_commands.guilds(discord.Object(id=config.bot_discord_admin_guild))
    async def test(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        logger.info("Test command: allow_send_message: %s",
                    self.bot.allow_send_message)
        # if self.bot.allow_send_message == True:
        await interaction.followup.send("Test command")

    @app_commands.command(name="sync")
    # type: ignore
    @app_commands.guilds(discord.Object(id=config.bot_discord_admin_guild))
    async def sync(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        logger.info("Syncing command tree")
        try:
            if config.environment == "development":
                logger.info("Syncing command tree to guild")
                await self.bot.tree.sync(guild=self.bot.admin_guild)
                await interaction.followup.send(f"{config.environment}: Synced command tree to guild")
            else:
                logger.info("Syncing command tree to all guilds")
                await self.bot.tree.sync()
                await interaction.followup.send(f"{config.environment}: Synced command tree to all guilds")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")
            await interaction.followup.send(f"{config.environment}: Failed to sync commands, check logs")


class AdminCommands(commands.Cog):
    def __init__(self, bot: DiscordBot):
        self.bot = bot

    @app_commands.command(name="test")
    # type: ignore
    @app_commands.guilds(discord.Object(id=config.bot_discord_admin_guild))
    async def test(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        logger.info("Test command: allow_send_message: %s",
                    self.bot.allow_send_message)
        # if self.bot.allow_send_message == True:
        await interaction.followup.send("Test command")

    @app_commands.command(name="sync")
    # type: ignore
    @app_commands.guilds(discord.Object(id=config.bot_discord_admin_guild))
    async def sync(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        logger.info("Syncing command tree")
        try:
            if config.environment == "development":
                logger.info("Syncing command tree to guild")
                await self.bot.tree.sync(guild=self.bot.admin_guild)
                await interaction.followup.send(f"{config.environment}: Synced command tree to guild")
            else:
                logger.info("Syncing command tree to all guilds")
                await self.bot.tree.sync()
                await interaction.followup.send(f"{config.environment}: Synced command tree to all guilds")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")
            await interaction.followup.send(f"{config.environment}: Failed to sync commands, check logs")


# Create a global instance of the bot
bot = DiscordBot()


async def main():
    """Main entry point for the Discord bot"""
    logger.info("Starting Discord bot...")

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)
    discord.utils.setup_logging(level=DEBUG)

    try:
        await bot.start(config.discord_bot_token)
    except Exception as e:
        logger.error(f"Error starting Discord bot: {e}")
    finally:
        # Wait for shutdown signal
        await shutdown_event.wait()
        logger.info("Shutting down Discord bot cleanly.")

        # Clean up resources
        await bot.cleanup()

        logger.info("Discord bot stopped")
