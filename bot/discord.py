import discord
from discord.ext import commands
from sqlalchemy import select
from .shared import ChannelSettingsDict, ContentDict, ScopedSession, logger, SessionLocal, handle_shutdown, shutdown_event
from app.models.db import BroadcasterSettings, Channels, ChannelSettings, ChatLog, Content, ContentQueue, ContentQueueSubmission, ExternalUser, AccountSource
import re
import asyncio

pending_vote_updates = {}
tracked_messages = set()
thread_to_message = {}

# URL regex pattern (basic)
URL_REGEX = r'(https?://[^\s]+)'

thread_timeout_minutes = 4320

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True
intents.reactions = True

session = ScopedSession()

bot = commands.Bot(command_prefix='$', intents=intents)

# Store the ID of the channel to listen to
listening_channel_id = None

async def schedule_vote_update(message: discord.Message, delay=2.0):
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
    )
    broadcaster_settings = session.execute(query).scalars().all()
    logger.info(f"Found {len(broadcaster_settings)} broadcaster settings with linked Discord channel")
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")

# @bot.tree.command(name="hello", description="Test hello command")
# async def hello(interaction: discord.Interaction, arg: str):
#     print(arg)
#     await interaction.response.send_message(f'Hello! {interaction.user.name} I added your clip to the queue!')

# Slash command to start listening to a channel
@bot.tree.command(name="listen", description="Start listening to this channel for messages")
async def listen(interaction: discord.Interaction):
    global listening_channel_id
    listening_channel_id = interaction.channel_id
    await interaction.response.send_message(f"✅ Now listening to messages in <#{interaction.channel_id}>")
    print(f"Listening to channel ID: {interaction.channel_id}")

@bot.event
async def on_message(message):
    await bot.process_commands(message)

    if message.author.bot:
        return

    # Print messages in the listening channel
    in_listening_channel = (
        listening_channel_id and message.channel.id == listening_channel_id
    )

    # Or in a thread whose parent is the listening channel
    in_thread_of_listening_channel = (
        isinstance(message.channel, discord.Thread)
        and message.channel.parent_id == listening_channel_id
    )

    if in_listening_channel or in_thread_of_listening_channel:
        logger.info(f"[{message.author.display_name}]: {message.content}")

    # Create thread if it's a URL message in the listening channel
    if in_listening_channel and re.search(URL_REGEX, message.content):
        try:
            await message.add_reaction("👍")
            await message.add_reaction("👎")

            thread = await message.create_thread(
                name=f"Clip from {message.author.display_name}",
                auto_archive_duration=thread_timeout_minutes,
            )
            await thread.send(f"✅ Added to queue \n 👍/👎 will affect queue priority \n 📣 Thread will notified and closed when clip is watched")
            logger.info(f"Thread created for message ID {message.id}")
            tracked_messages.add(message.id)
            thread_to_message[thread.id] = message.id
        except Exception as e:
            logger.error(f"Failed to create thread: {e}")

    # Handle "stop" messages in threads
    if isinstance(message.channel, discord.Thread):
        if message.content.strip().lower() == "stop":
            try:
                await message.channel.send("🛑 Stopping and closing this thread @here")
                await message.channel.edit(archived=True)
                original_msg_id = thread_to_message.pop(message.channel.id, None)
                if original_msg_id:
                    tracked_messages.discard(original_msg_id)
                logger.info(f"Thread '{message.channel.name}' closed by {message.author.display_name}")
            except Exception as e:
                logger.error(f"Error closing thread: {e}")

async def count_votes(message: discord.Message):
    votes = {"👍": 0, "👎": 0}

    for reaction in message.reactions:
        if str(reaction.emoji) in votes:
            count = 0
            async for user in reaction.users():
                if not user.bot:
                    count += 1
            votes[str(reaction.emoji)] = count

    logger.info(f"👍 Votes: {votes['👍']}, 👎 Votes: {votes['👎']}")
    return votes

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

