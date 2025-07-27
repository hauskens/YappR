"""
User service for handling user-related business logic.
"""
from typing import Iterable, Literal
from datetime import datetime

from sqlalchemy import select
from app.models import db
from app.models.user import Users, ExternalUser
from app.models.auth import Permissions, OAuth
from app.models.channel import Channels, ChannelModerator
from app.models.broadcaster import Broadcaster
from app.models.enums import PermissionType, AccountSource
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
                # Note: This would need Twitch API integration
                # from app.twitch_api import get_moderated_channels
                oauth = db.session.query(OAuth).filter_by(user_id=user.id).one_or_none()
                if oauth is None:
                    return []
                
                # moderated_channels = asyncio.run(get_moderated_channels(
                #     user.external_account_id, 
                #     user_token=oauth.token["access_token"], 
                #     refresh_token=oauth.token["refresh_token"]
                # ))
                
                logger.info(f"Would update moderated channels for {user.name}")
                
                # Placeholder implementation - would need actual Twitch API integration
                return []
                
            except Exception as e:
                logger.error(f"Failed to update moderated channels for {user.name}: {e}")
                return []
        else:
            return []
    
    @staticmethod
    def get_twitch_account_type(user: Users) -> Literal["partner", "affiliate", "regular"]:
        """Get Twitch account type for user."""
        if user.account_type == AccountSource.Twitch:
            if (config.debug == True and 
                config.debug_broadcaster_id is not None and 
                user.external_account_id == str(config.debug_broadcaster_id)):
                return "partner"
            
            # Note: This would need Twitch API integration
            # from app.twitch_api import get_twitch_user_by_id
            # twitch_user = asyncio.run(get_twitch_user_by_id(user.external_account_id))
            # logger.info(twitch_user.broadcaster_type)
            # if twitch_user.id == user.external_account_id:
            #     return twitch_user.broadcaster_type
            
            logger.info(f"Would get Twitch account type for {user.name}")
            
        return "regular"
    
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
    def ban_user(user_id: int, reason: str) -> Users:
        """Ban a user with a reason."""
        return UserService.update(user_id, banned=True, banned_reason=reason)
    
    @staticmethod
    def unban_user(user_id: int) -> Users:
        """Unban a user."""
        return UserService.update(user_id, banned=False, banned_reason=None)
    
    @staticmethod
    def update_last_login(user_id: int) -> Users:
        """Update user's last login timestamp."""
        return UserService.update(user_id, last_login=datetime.now())


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
               disabled: bool = False, ignore_weight_penalty: bool = False) -> ExternalUser:
        """Create a new external user."""
        external_user = ExternalUser(
            username=username,
            external_account_id=external_account_id,
            account_type=account_type,
            disabled=disabled,
            ignore_weight_penalty=ignore_weight_penalty
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