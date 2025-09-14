from twitchAPI.twitch import Twitch, AuthScope
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy import select
from app.models.auth import OAuth
from app.models.enums import ContentQueueSubmissionSource, AccountSource, ModerationActionType, ChannelRole
from app.models import Channels, ChannelSettings, Users, UserChannelRole
from app.models.chatlog import ChatLog
from app.models.config import config
import asyncio
import signal
import time
from datetime import datetime, date
from twitchAPI.type import AuthScope, ChatEvent
from twitchAPI.chat import Chat, ClearChatEvent, EventData, ChatMessage, ChatUser
from .shared import ChannelSettingsDict, ScopedSession, logger, SessionLocal, handle_shutdown, shutdown_event, task_manager, start_task_manager, url_pattern, get_platform, add_to_content_queue, _timeout_user
from functools import cache


class TwitchBot:
    def __init__(self):
        self.twitch = None
        self.session = None
        self.message_buffer: list[ChatLog] = []
        self.lock = asyncio.Lock()
        self.commit_interval = 5  # Commit every 5 seconds
        self.max_buffer_size = 100    # Commit when buffer reaches this size
        # Store channel info: {room_id: channel_id}
        self.enabled_channels: dict[str, int] = {}
        # Store channel settings: {channel_id: settings_dict}
        self.channel_settings: dict[int, ChannelSettingsDict] = {}
        self.last_commit_time = time.time()
        self.connected_channels = set()  # Keep track of channels we're already connected to
        self.channel_check_interval = 60  # Check for new channels every 60 seconds
        self.chat = None  # Reference to the chat object

        # Use the shared task manager instead of creating a separate Redis queue
        self.task_manager = task_manager

    async def init_bot(self):
        self.twitch = await Twitch(app_id=config.twitch_client_id, app_secret=config.twitch_client_secret)
        self.twitch.user_auth_refresh_callback = self.save_refresh_token

        # Initialize the session
        self.session = ScopedSession()

        logger.info("Twitch bot loading token")
        token_data = await self.load_token_from_db()
        logger.info("Twitch bot token loaded")
        if not token_data:
            logger.error("No bot OAuth token found in DB")
            raise Exception("No bot OAuth token found in DB")

        logger.info("Twitch bot setting authentication")
        await self.twitch.set_user_authentication(
            token=token_data['access_token'],
            refresh_token=token_data['refresh_token'],
            scope=[AuthScope.CHAT_READ,
                   AuthScope.CHAT_EDIT, AuthScope.CLIPS_EDIT],
        )
        logger.info("Twitch bot authentication set")

        # Start the background commit task
        asyncio.create_task(self.periodic_commit())

        # Start the periodic channel check task
        asyncio.create_task(self.periodic_channel_check())

        logger.info("Bot tasks initialized")

    async def load_token_from_db(self):
        with SessionLocal() as session:
            try:
                oauth = session.query(OAuth).filter_by(
                    provider='twitch_bot').one()
                return {
                    'access_token': oauth.token['access_token'],
                    'refresh_token': oauth.token['refresh_token']
                }
            except NoResultFound:
                logger.error("No bot OAuth token found in DB")
                raise Exception("No bot OAuth token found in DB")

    async def save_refresh_token(self, token: str, refresh_token: str):
        async with self.lock:
            with SessionLocal() as session:
                try:
                    oauth = session.query(OAuth).filter_by(
                        provider='twitch_bot').one()
                    oauth.token = {
                        "access_token": token,
                        "refresh_token": refresh_token
                    }
                    session.commit()
                    logger.info("Bot token refreshed and saved.")
                except Exception as e:
                    logger.error("Error saving refreshed token: %s", str(e))

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
            self.channel_settings = {}

            for channel in channels:
                channel_id = channel.id
                self.enabled_channels[channel.platform_channel_id] = channel_id

                # Store channel settings for quick access
                self.channel_settings[channel_id] = ChannelSettingsDict(
                    content_queue_enabled=channel.settings.content_queue_enabled if channel.settings else False,
                    chat_collection_enabled=channel.settings.chat_collection_enabled if channel.settings else False,
                    broadcaster_id=channel.broadcaster_id,
                )

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

        # Filter out channels we're already connected to
        new_channels = [
            channel for channel in channels if channel not in self.connected_channels]

        if not new_channels:
            logger.info('Already connected to all enabled channels')
            return

        logger.info('Joining channels: %s', new_channels)
        await ready_event.chat.join_room(new_channels)

        # Update our connected channels set
        self.connected_channels.update(new_channels)
        logger.info('Now connected to %d channels',
                    len(self.connected_channels))

    # this will be called whenever a message in a channel was send by either the bot OR another user
    async def on_message(self, msg: ChatMessage):
        if msg.room is None:
            logger.warning("Received message from unknown room: %s", msg)
            return
        try:
            room_id = msg.room.room_id

            # Look up channel_id from our in-memory dictionary
            if room_id not in self.enabled_channels:
                logger.warning(
                    "Received message from untracked room id: %s - %s", room_id, msg.room.name)
                return

            channel_id = self.enabled_channels[room_id]

            # Update user role based on badges
            await self._update_user_role_from_badges(msg, channel_id)

            if self.channel_settings and self.channel_settings[channel_id]['content_queue_enabled']:

                # Check for URLs in the message
                urls = url_pattern.findall(msg.text)
            
                # Only process URLs if content queue is enabled for this channel
                if urls:
                    for url in urls:
                        if get_platform(url):
                            logger.info("Found URL %s in message %s", url, msg.text, extra={
                                        "channel_id": channel_id})

                            # Extract user's message without the URL or replace URL with <link> based on position
                            user_comment = msg.text

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

                            await add_to_content_queue(
                                url=url,
                                username=msg.user.name,
                                external_user_id=msg.user.id,
                                submission_source_type=ContentQueueSubmissionSource.Twitch,
                                submission_source_id=int(room_id),
                                broadcaster_id=self.channel_settings[channel_id]['broadcaster_id'],
                                user_comment=user_comment if user_comment else None,
                                session=self.session
                            )

            if self.channel_settings[channel_id]['chat_collection_enabled']:

                # Create a new ChatLog entry
                chat_log = ChatLog(
                    channel_id=channel_id,
                    timestamp=datetime.fromtimestamp(
                        msg.sent_timestamp / 1000),
                    username=msg.user.name,
                    message=msg.text,
                    external_user_account_id=msg.user.id,
                )
                # Add to session and buffer
                self.session.add(chat_log)
                self.message_buffer.append(chat_log)

                # Flush to the database but don't commit yet
                self.session.flush()

                # Check if we should commit based on buffer size
                if len(self.message_buffer) >= self.max_buffer_size:
                    await self.commit_messages()

        except Exception as e:
            logger.error("Error processing chat message: %s - %s", e, msg)
            self.session.rollback()

    async def _record_moderation_event(self, target_user_id: str, target_username: str, action_type: ModerationActionType, channel_id: int, reason: str, duration_seconds: int | None = None):
        """Record a moderation event using a separate database session."""
        from app.models.user import Users, ModerationAction
        from app.models.enums import ModerationScope
        from datetime import datetime, timedelta
        
        # Use a completely separate session for moderation events
        with SessionLocal() as mod_session:
            try:
                # Get or create user
                user = mod_session.execute(
                    select(Users).filter_by(external_account_id=target_user_id)
                ).scalars().one_or_none()
                
                if not user:
                    # Create new user
                    user = Users(
                        name=target_username,
                        external_account_id=target_user_id,
                        account_type=AccountSource.Twitch,
                        disabled=False
                    )
                    mod_session.add(user)
                    mod_session.flush()  # Get the user ID
                else:
                    # Update username if it changed
                    if user.name != target_username:
                        user.name = target_username
                
                # Calculate expiration time for timeouts
                expires_at = None
                if duration_seconds:
                    expires_at = datetime.now() + timedelta(seconds=duration_seconds)
                
                # Create moderation action
                action = ModerationAction(
                    target_user_id=user.id,
                    action_type=action_type.value,
                    scope=ModerationScope.channel.value,
                    channel_id=channel_id,
                    reason=reason,
                    duration_seconds=duration_seconds,
                    expires_at=expires_at,
                    issued_at=datetime.now(),
                    active=True
                )
                
                mod_session.add(action)
                mod_session.commit()
                
            except Exception as e:
                mod_session.rollback()
                logger.error("Error recording moderation event: %s", e)
                raise

    async def _update_user_role_from_badges(self, msg: ChatMessage, channel_id: int):
        """Update user role based on Twitch badges from chat message."""
        from app.models.user import Users, UserChannelRole
        
        try:
            # Get badges from ChatUser.badges
            badges = msg.user.badges if hasattr(msg.user, 'badges') and msg.user.badges else {}
            
            # Map Twitch badges to our ChannelRole enum
            role = self._map_badges_to_role(badges, channel_id)
            
            if role:
                # send date with minute, second and microsecond set to 0 to bust cache every hour
                self._update_user_role(msg.user, channel_id, role, datetime.now().replace(minute=0, second=0, microsecond=0))
                
                        
        except Exception as e:
            logger.error("Error processing badges for role update: %s", e)

    @cache
    def _update_user_role(self, chat_user: ChatUser, channel_id: int, role: ChannelRole, _date_cached: datetime, clear_moderation_actions: bool = True):
        with SessionLocal() as role_session:
            try:
                # Get or create user
                user = role_session.execute(
                    select(Users).filter_by(external_account_id=chat_user.id)
                ).scalars().one_or_none()
                
                if not user:
                    # Create new user
                    user = Users(
                        name=chat_user.name,
                        external_account_id=chat_user.id,
                        account_type=AccountSource.Twitch,
                        disabled=False,
                        color=chat_user.color
                    )
                    role_session.add(user)
                    role_session.flush()
                else:
                    # Update username if it changed
                    if user.name != chat_user.name:
                        user.name = chat_user.name
                    if user.color != chat_user.color:
                        user.color = chat_user.color
                
                # Check existing role
                existing_role = role_session.execute(
                    select(UserChannelRole).filter_by(
                        user_id=user.id,
                        channel_id=channel_id,
                        active=True
                    )
                ).scalars().one_or_none()
                
                if existing_role:
                    # Update role if it changed
                    if existing_role.role != role.value:
                        existing_role.role = role.value
                        logger.debug(f"Updated role for user {chat_user.name} to {role.value} in channel {channel_id}")
                else:
                    # Create new role
                    new_role = UserChannelRole(
                        user_id=user.id,
                        channel_id=channel_id,
                        role=role.value,
                        granted_at=datetime.now(),
                        active=True
                    )
                    role_session.add(new_role)
                    logger.debug(f"Granted role {role.value} to user {chat_user.name} in channel {channel_id}")
                
                if clear_moderation_actions:
                    from app.models.user import ModerationAction
                    # check if user has active ban/timeout that can be cleared
                    existing_moderation_actions = role_session.execute(
                        select(ModerationAction).filter_by(
                            target_user_id=user.id,
                            channel_id=channel_id,
                            active=True
                        )
                    ).scalars().all()
                    for existing_moderation_action in existing_moderation_actions:
                        existing_moderation_action.active = False
                    
                role_session.commit()
            
            except Exception as e:
                role_session.rollback()
                logger.error("Error updating user role: %s", e)

    def _map_badges_to_role(self, badges: dict, channel_id: int) -> ChannelRole | None:
        """Map Twitch badges to ChannelRole enum."""
        
        # Check for broadcaster badge (channel owner)
        if 'broadcaster' in badges:
            return ChannelRole.Owner
        
        # Check for moderator badge
        if 'moderator' in badges:
            return ChannelRole.Mod
        
        # Check for VIP badge
        if 'vip' in badges:
            return ChannelRole.VIP
        
        # Check for subscriber badge
        if 'subscriber' in badges:
            return ChannelRole.Subscriber
        
        # For now, we can't detect followers from badges alone
        # Follower status would require API calls
        
        # Default to Basic role if no special badges
        return ChannelRole.Basic


    async def on_message_delete(self, delete_event: ClearChatEvent):
        """Handle message delete events (placeholder for future implementation)."""
        # Print all attributes of the delete_event object
        if delete_event.duration and delete_event.banned_user_id and delete_event.room_id:
            _timeout_user(delete_event.banned_user_id, delete_event.duration, int(delete_event.room_id), self.session, reason="Twitch moderator timeout")
        elif delete_event.banned_user_id and delete_event.room_id:
            _timeout_user(delete_event.banned_user_id, 0, int(delete_event.room_id), self.session, reason="Twitch moderator ban")
        else:
            logger.error("Invalid delete event: %s", delete_event)

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
                logger.error("Error in periodic commit: %s", e)

    async def commit_messages(self):
        """Commit buffered messages to the database"""
        if not self.message_buffer:
            return
        try:
            # Commit the session
            self.session.commit()

            # Clear the buffer and update the last commit time
            self.message_buffer.clear()
            self.last_commit_time = time.time()
        except Exception as e:
            logger.error("Error committing messages: %s", e)
            self.session.rollback()

    async def periodic_channel_check(self):
        """Periodically check for new channels to join and disconnect from channels no longer needed"""
        logger.info("Starting periodic channel check")
        while True:
            try:
                # Wait for the check interval
                await asyncio.sleep(self.channel_check_interval)

                # Make sure we have a chat reference
                if not self.chat:
                    logger.error("Chat reference not available")
                    continue

                # Get current enabled channels
                channels = self.get_enabled_twitch_channels()
                if not channels:
                    logger.info(
                        "No channels with chat collection enabled found")
                    # If we're connected to any channels, we should disconnect from all of them
                    if self.connected_channels:
                        channels_to_leave = list(self.connected_channels)
                        logger.info("Leaving all channels: %s",
                                    channels_to_leave)
                        await self.chat.leave_room(channels_to_leave)
                        self.connected_channels.clear()
                    continue

                # Find channels to join (new channels)
                new_channels = [
                    channel for channel in channels if channel not in self.connected_channels]

                # Find channels to leave (no longer in the enabled list)
                channels_to_leave = [
                    channel for channel in self.connected_channels if channel not in channels]

                # Join new channels if any
                if new_channels:
                    logger.info("Joining new channels: %s", new_channels)
                    await self.chat.join_room(new_channels)
                    self.connected_channels.update(new_channels)

                # Leave channels that are no longer enabled
                if channels_to_leave:
                    logger.info("Leaving channels: %s", channels_to_leave)
                    await self.chat.leave_room(channels_to_leave)
                    for channel in channels_to_leave:
                        self.connected_channels.remove(channel)

                if new_channels or channels_to_leave:
                    logger.info("Now connected to %s channels",
                                len(self.connected_channels))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in periodic channel check: %s", e)

    async def cleanup(self):
        """Clean up resources"""
        logger.info("Cleaning up resources")

        # Commit any pending changes
        if self.session:
            await self.commit_messages()

        # Close the session
        if self.session:
            self.session.close()


async def main():
    logger.info("Starting twitch bot...")

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    # Initialize the bot
    bot = TwitchBot()
    await bot.init_bot()

    # Initialize the task manager
    task_manager.init()

    # Register the bot with the task manager
    task_manager.register_component('twitch', bot)

    # Start the chat connection
    chat = await Chat(bot.twitch)
    chat.register_event(ChatEvent.READY, bot.on_ready)
    chat.register_event(ChatEvent.MESSAGE, bot.on_message)
    chat.register_event(ChatEvent.CHAT_CLEARED, bot.on_message_delete)
    chat.start()

    # Store chat reference in the bot for periodic channel check
    bot.chat = chat

    # Start the task manager in a background task
    task_manager_task = asyncio.create_task(start_task_manager())

    # Wait for shutdown signal
    await shutdown_event.wait()
    logger.info("Shutting down twitch bot cleanly.")

    # Clean up resources
    await bot.cleanup()
    chat.stop()

    # Cancel the task manager task
    if not task_manager_task.done():
        task_manager_task.cancel()
        try:
            await task_manager_task
        except asyncio.CancelledError:
            pass

    logger.info("Twitch bot stopped")
