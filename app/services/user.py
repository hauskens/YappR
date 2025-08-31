"""
User service for handling user-related business logic.
"""
from typing import Iterable, Sequence
from datetime import datetime
import asyncio

from sqlalchemy import select, or_, and_
from app.models import db
from app.models import Users, Permissions, Channels, Broadcaster, ChatLog
from app.models.user import UserChannelRole, ModerationAction
from app.models.enums import PermissionType, AccountSource, TwitchAccountType, PlatformType, ChannelRole, ModerationScope, ModerationActionType
from app.models.user import string_to_role, role_to_string
from app.models.config import config
from app.logger import logger
from app.services import ChannelService, BroadcasterService


class UserService:
    """Service class for user-related operations."""

    @staticmethod
    def get_by_id(user_id: int) -> Users:
        """Get user by ID."""
        return db.session.query(Users).filter_by(id=user_id).one()

    @staticmethod
    def get_by_external_id(external_id: str) -> Users:
        """Get user by external account ID."""
        return db.session.query(Users).filter_by(external_account_id=external_id).one()

    @staticmethod
    def get_all() -> list[Users]:
        """Get all users."""
        return db.session.query(Users).all()

    @staticmethod
    def get_permissions(user: Users) -> list[Permissions]:
        """Get all permissions for a user."""
        return db.session.query(Permissions).filter_by(user_id=user.id).all()

    @staticmethod
    def has_permission(user: Users, permissions: PermissionType | str | Iterable[PermissionType | str]) -> bool:
        """Check if user has specific permission(s)."""
        if isinstance(permissions, (PermissionType, str)):
            permissions = [permissions]

        permission_types: list[PermissionType] = [
            PermissionType(perm) if isinstance(perm, str) else perm
            for perm in permissions
        ]

        if user.banned_reason is None:
            return any(p.permission_type in permission_types for p in user.permissions)
        return False

    @staticmethod
    def has_broadcaster_id(user: Users, broadcaster_id: int) -> bool:
        """Check if user has access to a specific broadcaster."""
        return db.session.execute(
            select(Broadcaster)
            .join(Broadcaster.channels)
            .where(Channels.platform_channel_id == user.external_account_id, Broadcaster.id == broadcaster_id)
            .limit(1)
        ).scalars().one_or_none() is not None

    @staticmethod
    def is_moderator(user: Users, broadcaster_id: int | None = None) -> bool:
        """Check if user is a moderator (optionally for specific broadcaster)."""
        if broadcaster_id is None:
            return db.session.execute(
                select(UserChannelRole)
                .where(
                    UserChannelRole.user_id == user.id,
                    UserChannelRole.role == role_to_string(ChannelRole.Mod),
                    UserChannelRole.active == True
                )
                .limit(1)
            ).scalars().one_or_none() is not None
        else:
            channels = [channel.id for channel in BroadcasterService.get_channels(broadcaster_id)]
            return db.session.execute(
                select(UserChannelRole)
                .where(
                    UserChannelRole.user_id == user.id,
                    UserChannelRole.channel_id.in_(channels),
                    UserChannelRole.role == role_to_string(ChannelRole.Mod),
                    UserChannelRole.active == True
                )
                .limit(1)
            ).scalars().one_or_none() is not None

    @staticmethod
    def is_broadcaster(user: Users) -> bool:
        """Check if user is a broadcaster."""
        return db.session.execute(
            select(Broadcaster)
            .join(Broadcaster.channels)
            .where(Channels.platform_channel_id == user.external_account_id)
            .limit(1)
        ).scalars().one_or_none() is not None

    @staticmethod
    def is_admin(user: Users) -> bool:
        """Check if user is an admin."""
        return db.session.query(Permissions).filter_by(user_id=user.id, permission_type=PermissionType.Admin).one_or_none() is not None

    @staticmethod
    def get_broadcaster(user: Users) -> Broadcaster | None:
        """Get broadcaster instance for user if they are a broadcaster."""
        return db.session.execute(
            select(Broadcaster)
            .join(Broadcaster.channels)
            .where(Channels.platform_channel_id == user.external_account_id)
            .limit(1)
        ).scalars().one_or_none()

    @staticmethod
    def add_permissions(user: Users, permission_type: PermissionType):
        """Add permission to user if they don't already have it."""
        if not UserService.has_permission(user, permission_type):
            db.session.add(
                Permissions(user_id=user.id, permission_type=permission_type)
            )
            db.session.commit()
            logger.info(f"Granted {permission_type.name} to {user.name}!")

    @staticmethod
    def update_moderated_channels(user: Users) -> list:
        """Update moderated channels for Twitch users."""
        if user.account_type == AccountSource.Twitch:
            try:
                from app.services.platform import PlatformServiceRegistry
                platform_service = PlatformServiceRegistry.get_service(
                    PlatformType.Twitch)
                if platform_service is None:
                    raise ValueError("Twitch platform service not found")

                channels = asyncio.run(
                    platform_service.fetch_moderated_channels(user))
                logger.debug("Updating moderated channels for user", extra={"user": user.name})
                
                # Get existing channel roles for this user
                existing_roles = db.session.execute(
                    select(UserChannelRole)
                    .where(
                        UserChannelRole.user_id == user.id,
                        UserChannelRole.role == role_to_string(ChannelRole.Mod),
                        UserChannelRole.active == True
                    )
                ).scalars().all()
                
                existing_channel_ids = {role.channel_id for role in existing_roles}
                logger.debug("Found %s existing moderated channels for user", len(existing_channel_ids), extra={"user": user.name})
                
                # Get channel IDs from Twitch API
                logger.debug("Found %s channels from Twitch API", len(channels), extra={"user": user.name})
                new_channel_ids = {channel.id for channel in channels}
                
                # Revoke roles for channels user no longer moderates
                channels_to_revoke = existing_channel_ids - new_channel_ids
                for channel_id in channels_to_revoke:
                    UserService.revoke_channel_role(user.id, channel_id)
                    logger.debug("Revoked moderator role from channel %s", channel_id, extra={"user": user.name})
                
                # Grant roles for new moderated channels
                channels_to_grant = new_channel_ids - existing_channel_ids
                logger.debug("Found %s new moderated channels for user", len(channels_to_grant), extra={"user": user.name})
                for channel in channels:
                    if channel.id in channels_to_grant:
                        UserService.grant_channel_role(user.id, channel.id, ChannelRole.Mod)
                        logger.debug("Granted moderator role for channel %s", channel.name, extra={"channel": channel.name})
                
                logger.debug("Updated moderated channels for user - granted: %s, revoked: %s", 
                           len(channels_to_grant), len(channels_to_revoke), extra={"user": user.name})
                return channels

            except Exception as e:
                logger.error(
                    "Failed to update moderated channels for user", extra={"user": user.name, "error": str(e)})
                return []
        else:
            return []

    @staticmethod
    def get_moderated_channels(user: Users) -> list[str]:
        """Get moderated channels for user."""
        return asyncio.run(UserService.fetch_moderated_channels(user))

    @staticmethod
    def get_moderated_channels_from_db(user: Users) -> list[Channels]:
        """Get moderated channels from database (no API call)."""
        moderated_roles = db.session.execute(
            select(UserChannelRole)
            .where(
                UserChannelRole.user_id == user.id,
                UserChannelRole.role == role_to_string(ChannelRole.Mod),
                UserChannelRole.active == True
            )
        ).scalars().all()
        
        channels = []
        for role_record in moderated_roles:
            channel = db.session.get(Channels, role_record.channel_id)
            if channel:
                channels.append(channel)
        
        return channels

    @staticmethod
    async def fetch_moderated_channels(user: Users) -> list[str]:
        """Fetch moderated channels for user."""
        if user.account_type == AccountSource.Twitch:
            from app.twitch_client_factory import TwitchClientFactory
            from app.twitch_api import get_moderated_channels
            try:
                twitch_client = await TwitchClientFactory.get_user_client(user)
                channels = await get_moderated_channels(user.external_account_id, api_client=twitch_client)
                return channels
            except Exception as e:
                logger.error(
                    "Failed to fetch moderated channels for user", extra={"user": user.name, "error": str(e)})
                return []
        else:
            return []

    @staticmethod
    def get_twitch_account_type(user: Users) -> TwitchAccountType:
        """Get Twitch account type for user."""
        from app.services.platform import TwitchPlatformService
        if user.account_type == AccountSource.Twitch:
            if (config.debug == True and
                config.debug_broadcaster_id is not None and
                    user.external_account_id == str(config.debug_broadcaster_id)):
                return TwitchAccountType.Partner

            return TwitchPlatformService().fetch_account_type(user)
        return TwitchAccountType.Regular

    @staticmethod
    def create(name: str, external_account_id: str | None, account_type: AccountSource,
               avatar_url: str | None = None) -> Users:
        """Create a new user."""
        user = Users(
            name=name,
            external_account_id=external_account_id,
            account_type=account_type,
            avatar_url=avatar_url
        )
        db.session.add(user)
        db.session.commit()
        logger.info(f"Created user: {name}")
        return user

    @staticmethod
    def get_or_create(name: str, external_account_id: str | None, account_type: AccountSource,
                     avatar_url: str | None = None) -> Users:
        """Get user by external_account_id or create if not exists."""
        user = None
        
        # Try to find existing user by external_account_id
        if external_account_id:
            user = db.session.query(Users).filter_by(external_account_id=external_account_id).one_or_none()
        
        if user:
            # Update user fields if they have changed
            updated = False
            if user.name != name:
                user.name = name
                updated = True
            if avatar_url and user.avatar_url != avatar_url:
                user.avatar_url = avatar_url
                updated = True
                
            if updated:
                db.session.commit()
                logger.info(f"Updated user fields for: {name}")
            return user
        
        # Create new user if not found
        return UserService.create(name, external_account_id, account_type, avatar_url)

    @staticmethod
    def update(user_id: int, **kwargs) -> Users:
        """Update user fields."""
        user = UserService.get_by_id(user_id)
        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)
        db.session.commit()
        return user

    @staticmethod
    def update_last_login(user_id: int) -> Users:
        """Update user's last login timestamp."""
        return UserService.update(user_id, last_login=datetime.now())

    @staticmethod
    def match_chatlog_users(batch_size: int = 1000, progress_callback=None) -> dict:
        """
        Match ChatLogs without external_user_account_id to Users with Twitch accounts.
        
        This function is designed to be generic and can be used as a Celery task.
        
        Args:
            batch_size: Number of ChatLog records to process per batch
            progress_callback: Optional callback function for progress updates
                             Should accept (current, total, message) parameters
        
        Returns:
            Dictionary with matching results and statistics
        """
        from sqlalchemy import text, update, func
        
        results = {
            'status': 'success',
            'total_unmatched': 0,
            'total_processed': 0,
            'total_matched': 0,
            'total_updated': 0,
            'errors': [],
            'started_at': datetime.now().isoformat(),
            'completed_at': None
        }
        
        try:
            # Step 1: Count total unmatched chatlogs for progress tracking
            total_unmatched = db.session.query(func.count(ChatLog.id)).filter(
                ChatLog.external_user_account_id.is_(None)
            ).scalar()
            
            results['total_unmatched'] = total_unmatched
            logger.info(f"Starting ChatLog matching process - {total_unmatched:,} unmatched records found")
            
            if total_unmatched == 0:
                results['completed_at'] = datetime.now().isoformat()
                if progress_callback:
                    progress_callback(0, 0, "No unmatched ChatLogs found")
                return results
            
            # Step 2: Load all Twitch users into memory for fast lookups
            logger.info("Loading Twitch users into memory")
            twitch_users = db.session.query(Users.name, Users.external_account_id).filter(
                Users.account_type == AccountSource.Twitch
            ).all()
            
            # Create username -> external_account_id mapping for O(1) lookups
            username_to_external_id = {user.name.lower(): user.external_account_id for user in twitch_users}
            logger.info(f"Loaded {len(username_to_external_id):,} Twitch users for matching")
            
            if not username_to_external_id:
                results['status'] = 'warning'
                results['errors'].append("No Twitch users found in database")
                results['completed_at'] = datetime.now().isoformat()
                return results
            
            # Step 3: Process ChatLogs in batches
            processed = 0
            matched_count = 0
            offset = 0
            
            while processed < total_unmatched:
                # Get batch of unmatched chatlogs
                chatlog_batch = db.session.query(
                    ChatLog.id, ChatLog.username
                ).filter(
                    ChatLog.external_user_account_id.is_(None)
                ).offset(offset).limit(batch_size).all()
                
                if not chatlog_batch:
                    break
                
                # Find matches in this batch
                batch_updates = []
                batch_matched = 0
                
                for chatlog_id, username in chatlog_batch:
                    # Case-insensitive username matching
                    normalized_username = username.lower()
                    if normalized_username in username_to_external_id:
                        external_id = username_to_external_id[normalized_username]
                        batch_updates.append({
                            'chatlog_id': chatlog_id, 
                            'external_user_account_id': int(external_id)
                        })
                        batch_matched += 1
                
                # Bulk update the matches found in this batch
                if batch_updates:
                    try:
                        # Use bulk update for efficiency
                        for update_data in batch_updates:
                            db.session.execute(
                                update(ChatLog)
                                .where(ChatLog.id == update_data['chatlog_id'])
                                .values(external_user_account_id=update_data['external_user_account_id'])
                            )
                        db.session.commit()
                        results['total_updated'] += len(batch_updates)
                        
                    except Exception as e:
                        db.session.rollback()
                        error_msg = f"Error updating batch at offset {offset}: {str(e)}"
                        results['errors'].append(error_msg)
                        logger.error(error_msg)
                
                # Update progress
                processed += len(chatlog_batch)
                matched_count += batch_matched
                results['total_processed'] = processed
                results['total_matched'] = matched_count
                
                # Call progress callback if provided
                if progress_callback:
                    progress_msg = f"Processed {processed:,}/{total_unmatched:,} records, matched {matched_count:,}"
                    progress_callback(processed, total_unmatched, progress_msg)
                
                # Log progress periodically
                if processed % (batch_size * 10) == 0 or processed >= total_unmatched:
                    logger.info(f"Progress: {processed:,}/{total_unmatched:,} processed, {matched_count:,} matched, {results['total_updated']:,} updated")
                
                offset += batch_size
            
            results['completed_at'] = datetime.now().isoformat()
            logger.info(f"ChatLog matching completed - {results['total_matched']:,} matches found, {results['total_updated']:,} records updated")
            
        except Exception as e:
            db.session.rollback()
            results['status'] = 'error'
            error_msg = f"Fatal error during matching process: {str(e)}"
            results['errors'].append(error_msg)
            results['completed_at'] = datetime.now().isoformat()
            logger.error(error_msg, exc_info=True)
        
        return results

    # Role Management Methods
    @staticmethod
    def get_channel_role(user: Users, channel_id: int) -> ChannelRole | None:
        """Get user's role in a specific channel."""
        channel = ChannelService.get_by_id(channel_id)
        if user.broadcaster_id == channel.broadcaster_id:
            return ChannelRole.Owner
        
        role_record = db.session.execute(
            select(UserChannelRole)
            .where(
                UserChannelRole.user_id == user.id,
                UserChannelRole.channel_id == channel_id,
                UserChannelRole.active == True
            )
        ).scalar_one_or_none()
        
        return string_to_role(role_record.role) if role_record else None

    @staticmethod
    def has_channel_permission(user: Users, channel_id: int, required_roles: list[ChannelRole]) -> bool:
        """Check if user has any of the required roles in a channel."""
        current_role = UserService.get_channel_role(user, channel_id)
        return current_role in required_roles if current_role else False

    @staticmethod
    def grant_channel_role(user_id: int, channel_id: int, role: ChannelRole, 
                          granted_by_user_id: int | None = None, 
                          expires_at: datetime | None = None) -> UserChannelRole:
        """Grant or update a user's role in a specific channel."""
        existing_role = db.session.execute(
            select(UserChannelRole)
            .where(
                UserChannelRole.user_id == user_id,
                UserChannelRole.channel_id == channel_id
            )
        ).scalar_one_or_none()
        
        if existing_role:
            existing_role.role = role_to_string(role)
            existing_role.granted_by = granted_by_user_id
            existing_role.granted_at = datetime.now()
            existing_role.expires_at = expires_at
            existing_role.active = True
            role_record = existing_role
        else:
            role_record = UserChannelRole(
                user_id=user_id,
                channel_id=channel_id,
                role=role_to_string(role),
                granted_by=granted_by_user_id,
                expires_at=expires_at
            )
            db.session.add(role_record)
        
        db.session.commit()
        logger.info(f"Granted role {role.value} to user {user_id} in channel {channel_id}")
        return role_record

    @staticmethod
    def revoke_channel_role(user_id: int, channel_id: int) -> bool:
        """Revoke a user's role in a specific channel."""
        role_record = db.session.execute(
            select(UserChannelRole)
            .where(
                UserChannelRole.user_id == user_id,
                UserChannelRole.channel_id == channel_id,
                UserChannelRole.active == True
            )
        ).scalar_one_or_none()
        
        if role_record:
            role_record.active = False
            db.session.commit()
            logger.info(f"Revoked role from user {user_id} in channel {channel_id}")
            return True
        return False

    @staticmethod
    def get_channel_users_by_role(channel_id: int, role: ChannelRole | None = None) -> Sequence[Users]:
        """Get users in a channel, optionally filtered by role."""
        query = select(Users).join(UserChannelRole).where(
            UserChannelRole.channel_id == channel_id,
            UserChannelRole.active == True
        )
        
        if role:
            query = query.where(UserChannelRole.role == role_to_string(role))
        
        return db.session.execute(query).scalars().all()

    # Moderation Methods
    @staticmethod
    def is_banned_from_channel(user: Users, channel_id: int) -> bool:
        """Check if user is banned from a specific channel."""
        if user.globally_banned:
            if user.global_ban_expires_at is None:  # Permanent
                return True
            if user.global_ban_expires_at > datetime.now():  # Active temporary
                return True
        
        # Check channel-specific ban
        active_ban = db.session.execute(
            select(ModerationAction)
            .where(
                ModerationAction.target_user_id == user.id,
                ModerationAction.action_type == ModerationActionType.ban,
                ModerationAction.scope == ModerationScope.channel,
                ModerationAction.channel_id == channel_id,
                ModerationAction.active == True,
                or_(
                    ModerationAction.expires_at.is_(None),
                    ModerationAction.expires_at > datetime.now()
                )
            )
        ).scalar_one_or_none()
        
        return active_ban is not None

    @staticmethod
    def is_globally_banned(user: Users) -> bool:
        """Check if user is globally banned."""
        if not user.globally_banned:
            return False
        
        if user.global_ban_expires_at is None:  # Permanent
            return True
        
        return user.global_ban_expires_at > datetime.now()

    @staticmethod
    def get_active_moderation_actions(user: Users, channel_id: int | None = None) -> Sequence[ModerationAction]:
        """Get all active moderation actions for this user."""
        query = select(ModerationAction).where(
            ModerationAction.target_user_id == user.id,
            ModerationAction.active == True,
            or_(
                ModerationAction.expires_at.is_(None),
                ModerationAction.expires_at > datetime.now()
            )
        )
        
        if channel_id is not None:
            query = query.where(
                or_(
                    ModerationAction.scope == ModerationScope.global_,
                    and_(
                        ModerationAction.scope == ModerationScope.channel,
                        ModerationAction.channel_id == channel_id
                    )
                )
            )
        
        return db.session.execute(query).scalars().all()




# For template accessibility, create simple function interfaces
def get_user_service() -> UserService:
    """Get user service instance for use in templates."""
    return UserService()


def user_has_permission(user: Users, permissions: PermissionType | str | Iterable[PermissionType | str]) -> bool:
    """Check user permissions for use in templates."""
    return UserService.has_permission(user, permissions)


def user_is_moderator(user: Users, broadcaster_id: int | None = None) -> bool:
    """Check if user is moderator for use in templates."""
    return UserService.is_moderator(user, broadcaster_id)


def user_is_broadcaster(user: Users) -> bool:
    """Check if user is broadcaster for use in templates."""
    return UserService.is_broadcaster(user)


def user_get_broadcaster(user: Users) -> Broadcaster | None:
    """Get user's broadcaster for use in templates."""
    return UserService.get_broadcaster(user)
