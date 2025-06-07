import discord
from discord import Message
from discord.ext import commands
from sqlalchemy import select
from .shared import ScopedSession, logger, url_pattern, add_to_content_queue, get_platform, update_submission_weight
from app.models.db import BroadcasterSettings, ContentQueueSubmissionSource
import re
import asyncio
from typing import Literal

pending_vote_updates: dict[int, asyncio.Task] = {}
tracked_messages: set[int] = set()
thread_to_message: dict[int, int] = {}

thread_timeout_minutes: Literal[60, 1440, 4320, 10080] = 4320

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True
intents.reactions = True

session = ScopedSession()

bot = commands.Bot(command_prefix='$', intents=intents)

# Store the IDs of channels to listen to
active_listening_channels: set[int] = set()

async def schedule_vote_update(message: Message, delay=2.0):
    # If there's already a task running for this message, skip
    if message.id in pending_vote_updates:
        return

    async def debounced():
        await asyncio.sleep(delay)
        await count_votes(message)
        del pending_vote_updates[message.id]

    # Schedule the debounced vote count
    task = asyncio.create_task(debounced())
    pending_vote_updates[message.id] = task

@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')
    query = select(BroadcasterSettings).where(
        BroadcasterSettings.linked_discord_channel_id.isnot(None),
        BroadcasterSettings.linked_discord_channel_verified == True
    )
    broadcaster_settings = session.execute(query).scalars().all()
    logger.info(f"Found {len(broadcaster_settings)} verified broadcaster settings with linked Discord channel")
    
    # Join all verified linked Discord channels
    for setting in broadcaster_settings:
        try:
            channel = bot.get_channel(setting.linked_discord_channel_id)
            if channel:
                active_listening_channels.add(setting.linked_discord_channel_id)
                logger.info(f"Joined verified channel: {channel.name} (ID: {channel.id})")
            else:
                logger.warning(f"Could not find channel with ID: {setting.linked_discord_channel_id}")
        except Exception as e:
            logger.error(f"Failed to join channel {setting.linked_discord_channel_id}: {e}")
    
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")


# Slash command to start listening to a channel and verify the broadcaster
@bot.tree.command(name="verify", description="Verify this channel in YappR")
async def verify(interaction: discord.Interaction):
    # Find broadcaster settings with this channel ID
    logger.info(f"Verifying channel {interaction.channel_id}")
    if interaction.channel_id is not None and interaction.channel_id in active_listening_channels:
        await interaction.response.send_message(f"✅ This channel is already verified")
        return
    
    query = select(BroadcasterSettings).where(
        BroadcasterSettings.linked_discord_channel_id == interaction.channel_id
    )
    broadcaster_setting = session.execute(query).scalars().first()
    
    if broadcaster_setting and interaction.channel_id is not None:
        # Verify the channel
        broadcaster_setting.linked_discord_channel_verified = True
        session.commit()
        
        # Add to active listening channels
        active_listening_channels.add(interaction.channel_id)
        
        await interaction.response.send_message(f"✅ Channel verified and now listening to messages in <#{interaction.channel_id}>")
        logger.info(f"Channel {interaction.channel_id} verified and listening started by {interaction.user.name}", extra={"broadcaster_id": broadcaster_setting.broadcaster_id})
    else:
        # No broadcaster found with this channel ID
        await interaction.response.send_message(f"❌ This discord channel is not linked to a broadcaster. In YappR, go to a broadcaster and add the channel id `{interaction.channel_id}`.")
        logger.info(f"Channel {interaction.channel_id} is not linked to a broadcaster")

@bot.event
async def on_message(message: Message):
    await bot.process_commands(message)

    if message.author.bot:
        return

    # Check if message is in an active listening channel
    in_listening_channel = message.channel.id in active_listening_channels

    # Or in a thread whose parent is an active listening channel
    in_thread_of_listening_channel = (
        isinstance(message.channel, discord.Thread)
        and message.channel.parent_id in active_listening_channels
    )

    if in_listening_channel or in_thread_of_listening_channel:
        logger.info(f"[{message.author.display_name}]: {message.content}")

    # Process URL messages in the listening channel
    if in_listening_channel and re.search(url_pattern, message.content):
        query = select(BroadcasterSettings).where(
            BroadcasterSettings.linked_discord_channel_id == message.channel.id
        )
        broadcaster_setting = session.execute(query).scalars().one_or_none()
        if broadcaster_setting is None:
            logger.error(f"No broadcaster setting found for channel {message.channel.id}")
            return
        
        # Check for URLs in the message
        urls = url_pattern.findall(message.content)
        
        # Only process URLs if content queue is enabled for this channel
        if urls:
            for url in urls:
                if get_platform(url):
                    logger.info("Found URL %s in message %s", url, message.content, extra={"channel_id": broadcaster_setting.broadcaster_id})

                    # Add the URL to the content queue
                    await add_to_content_queue(url, broadcaster_setting.broadcaster_id, message.author.display_name, str(message.author.id), ContentQueueSubmissionSource.Discord, message.id)
        
        # Create a thread if enabled
        if broadcaster_setting.linked_discord_threads_enabled:
            try:
                thread = await message.create_thread(
                    name=f"Clip from {message.author.display_name}",
                    auto_archive_duration=thread_timeout_minutes,
                )
                logger.info(f"Thread created for message ID {message.id}")
                tracked_messages.add(message.id)
                thread_to_message[thread.id] = message.id
            except Exception as e:
                logger.error(f"Failed to create thread: {e}")
        else:
            tracked_messages.add(message.id)


async def count_votes(message: discord.Message):
    unique_users = set()
    for reaction in message.reactions:
        async for user in reaction.users():
            if not user.bot:
                unique_users.add(user.id)

    logger.info(f"Counted {len(unique_users)} unique users for message ID {message.id}")
    await update_submission_weight(message.id, len(unique_users))
    return len(unique_users)


@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return
    if payload.message_id not in tracked_messages:
        return

    channel = await bot.fetch_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)
    await schedule_vote_update(message)

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.user_id == bot.user.id:
        return
    if payload.message_id not in tracked_messages:
        return

    channel = await bot.fetch_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)
    await schedule_vote_update(message)

