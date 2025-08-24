"""
User service for handling user-related business logic.
"""
from typing import Iterable, Sequence
from datetime import datetime
import asyncio

from sqlalchemy import select, or_, and_
from app.models import db
from app.models import Users, ExternalUser, Permissions, Channels, ChannelModerator, Broadcaster
from app.models.user import UserChannelRole, ModerationAction
from app.models.enums import PermissionType, AccountSource, TwitchAccountType, PlatformType, ChannelRole, ModerationScope, ModerationActionType
from app.models.user import string_to_role, role_to_string
from app.models.config import config
from app.logger import logger


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
            return db.session.query(ChannelModerator).filter_by(user_id=user.id).one_or_none() is not None
        else:
            return db.session.query(ChannelModerator).filter_by(user_id=user.id, channel_id=broadcaster_id).one_or_none() is not None

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
                existing_channel_moderators = db.session.query(ChannelModerator).filter_by(user_id=user.id).all()
                logger.debug("Found %s moderated channels for user", len(existing_channel_moderators), extra={"user": user.name})
                if len(existing_channel_moderators) > 0:
                    db.session.delete(existing_channel_moderators)
                logger.debug("Deleted %s moderated channels for user", len(existing_channel_moderators), extra={"user": user.name})
                db.session.flush()
                for channel in channels:
                    logger.debug("Adding channel %s to user", channel.name, extra={"channel": channel.name})
                    db.session.add(ChannelModerator(
                        user_id=user.id, channel_id=channel.id))
                db.session.commit()
                logger.debug("Updated %s moderated channels for user", len(channels), extra={"user": user.name})

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
               avatar_url: str | None = None, broadcaster_id: int | None = None) -> Users:
        """Create a new user."""
        user = Users(
            name=name,
            external_account_id=external_account_id,
            account_type=account_type,
            avatar_url=avatar_url,
            broadcaster_id=broadcaster_id
        )
        db.session.add(user)
        db.session.commit()
        logger.info(f"Created user: {name}")
        return user

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

    # Role Management Methods
    @staticmethod
    def get_channel_role(user: Users, channel_id: int) -> ChannelRole | None:
        """Get user's role in a specific channel."""
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


class ExternalUserService:
    """Service class for external user-related operations."""

    @staticmethod
    def get_by_id(external_user_id: int) -> ExternalUser:
        """Get external user by ID."""
        return db.session.query(ExternalUser).filter_by(id=external_user_id).one()

    @staticmethod
    def get_by_external_id(external_account_id: int, account_type: AccountSource) -> ExternalUser | None:
        """Get external user by external account ID and type."""
        return db.session.query(ExternalUser).filter_by(
            external_account_id=external_account_id,
            account_type=account_type
        ).one_or_none()

    @staticmethod
    def create(username: str, external_account_id: int | None, account_type: AccountSource,
               disabled: bool = False) -> ExternalUser:
        """Create a new external user."""
        external_user = ExternalUser(
            username=username,
            external_account_id=external_account_id,
            account_type=account_type,
            disabled=disabled,
        )
        db.session.add(external_user)
        db.session.commit()
        logger.info(f"Created external user: {username}")
        return external_user

    @staticmethod
    def update(external_user_id: int, **kwargs) -> ExternalUser:
        """Update external user fields."""
        external_user = ExternalUserService.get_by_id(external_user_id)
        for key, value in kwargs.items():
            if hasattr(external_user, key):
                setattr(external_user, key, value)
        db.session.commit()
        return external_user

    @staticmethod
    def disable_user(external_user_id: int) -> ExternalUser:
        """Disable an external user."""
        return ExternalUserService.update(external_user_id, disabled=True)

    @staticmethod
    def enable_user(external_user_id: int) -> ExternalUser:
        """Enable an external user."""
        return ExternalUserService.update(external_user_id, disabled=False)


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
