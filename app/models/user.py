from sqlalchemy import String, Integer, Boolean, ForeignKey, DateTime, Text, Enum, Float, BigInteger, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from dataclasses import dataclass
from .base import Base
from .enums import AccountSource, UserCreationType, ChannelRole, ModerationActionType, ModerationScope
from flask_login import UserMixin  # type: ignore
from pydantic import BaseModel, Field, HttpUrl
from typing import TYPE_CHECKING, Optional, List, Dict

if TYPE_CHECKING:
    from .broadcaster import Broadcaster
    from .content_queue import ContentQueueSubmission
    from .auth import Permissions, OAuth
    from .channel import ChannelModerator, Channels

class UserBase(BaseModel):
    id: int
    name: str = Field(..., max_length=500)
    external_account_id: str = Field(..., max_length=500)
    account_type: AccountSource
    first_login: datetime
    last_login: datetime
    avatar_url: HttpUrl | None = Field(..., max_length=500)
    broadcaster_id: int | None
    banned: bool = Field(default=False)
    banned_reason: str | None

class Users(Base, UserMixin):
    __tablename__: str = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(500))
    external_account_id: Mapped[str] = mapped_column(
        String(500), unique=True, nullable=False
    )
    account_type: Mapped[str] = mapped_column(Enum(AccountSource))
    first_login: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now())
    last_login: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now())
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    broadcaster_id: Mapped[int | None] = mapped_column(
        ForeignKey("broadcaster.id"))
    banned: Mapped[bool] = mapped_column(Boolean, default=False)
    banned_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # New moderation fields
    globally_banned: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false')
    global_ban_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    global_ban_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Global app permissions
    permissions: Mapped[list["Permissions"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    channel_moderators: Mapped[list["ChannelModerator"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    oauth: Mapped[list["OAuth"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    
    # New role and moderation relationships
    channel_roles: Mapped[List["UserChannelRole"]] = relationship(
        "UserChannelRole", 
        foreign_keys="UserChannelRole.user_id",
        back_populates="user", 
        cascade="all, delete-orphan"
    )
    moderation_actions_received: Mapped[List["ModerationAction"]] = relationship(
        "ModerationAction", 
        foreign_keys="ModerationAction.target_user_id",
        back_populates="target_user"
    )
    moderation_actions_issued: Mapped[List["ModerationAction"]] = relationship(
        "ModerationAction",
        foreign_keys="ModerationAction.issued_by",
        back_populates="issued_by_user"
    )


class ExternalUser(Base):
    __tablename__ = "external_users"
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(600), nullable=False)
    external_account_id: Mapped[int | None] = mapped_column(
        BigInteger, unique=True, nullable=True
    )
    account_type: Mapped[AccountSource] = mapped_column(Enum(AccountSource))
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    ignore_weight_penalty: Mapped[bool] = mapped_column(Boolean, default=False)
    submissions: Mapped[list["ContentQueueSubmission"]
                        ] = relationship(back_populates="user")
    weights: Mapped[list["ExternalUserWeight"]] = relationship(
        back_populates="external_user")


class ExternalUserWeight(Base):
    __tablename__ = "external_user_weights"
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True)
    external_user_id: Mapped[int] = mapped_column(
        ForeignKey("external_users.id"))
    external_user: Mapped["ExternalUser"] = relationship(
        back_populates="weights")
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    broadcaster_id: Mapped[int] = mapped_column(ForeignKey("broadcaster.id"))
    broadcaster: Mapped["Broadcaster"] = relationship()
    banned: Mapped[bool] = mapped_column(Boolean, default=False)
    banned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    unban_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UserChannelRole(Base):
    """User roles within specific channels."""
    __tablename__ = "user_channel_roles"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=False)
    role: Mapped[str] = mapped_column(
        String(50), default=ChannelRole.Basic.value, server_default=ChannelRole.Basic.value
    )
    
    # Tracking
    granted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default='now()')
    granted_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Status
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default='true')
    
    # Relationships
    user: Mapped["Users"] = relationship(
        "Users", 
        foreign_keys=[user_id],
        back_populates="channel_roles"
    )
    channel: Mapped["Channels"] = relationship("Channels")
    granted_by_user: Mapped[Optional["Users"]] = relationship(
        "Users", foreign_keys=[granted_by]
    )
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('user_id', 'channel_id', name='uq_user_channel'),
    )


class ModerationAction(Base):
    """Track all moderation actions (bans, timeouts, warnings)."""
    __tablename__ = "moderation_actions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    action_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    
    # Scope
    scope: Mapped[str] = mapped_column(String(50), nullable=False)
    channel_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("channels.id"), nullable=True
    )
    
    # Action details
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Tracking
    issued_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default='now()')
    
    # Status
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default='true')
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    revoked_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    target_user: Mapped["Users"] = relationship(
        "Users", 
        foreign_keys=[target_user_id], 
        back_populates="moderation_actions_received"
    )
    channel: Mapped[Optional["Channels"]] = relationship("Channels")
    issued_by_user: Mapped["Users"] = relationship(
        "Users", 
        foreign_keys=[issued_by], 
        back_populates="moderation_actions_issued"
    )
    revoked_by_user: Mapped[Optional["Users"]] = relationship(
        "Users", 
        foreign_keys=[revoked_by]
    )
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            '(scope = \'global\' AND channel_id IS NULL) OR (scope = \'channel\' AND channel_id IS NOT NULL)',
            name='check_scope_channel_consistency'
        ),
    )


@dataclass
class RoleConfig:
    """Configuration for channel roles including display information."""
    description: str
    background_color: str
    text_color: str
    priority: int  # Higher number = higher priority/authority


# Role configuration mapping
ROLE_CONFIGS: Dict[ChannelRole, RoleConfig] = {
    ChannelRole.Owner: RoleConfig(
        description="Channel owner with full administrative privileges",
        background_color="#ff6b6b",  # Red
        text_color="#ffffff",
        priority=100
    ),
    ChannelRole.Mod: RoleConfig(
        description="Channel moderator with moderation privileges",
        background_color="#4ecdc4",  # Teal
        text_color="#ffffff", 
        priority=90
    ),
    ChannelRole.VIP: RoleConfig(
        description="VIP member with special privileges",
        background_color="#ffe66d",  # Yellow
        text_color="#2c3e50",
        priority=80
    ),
    ChannelRole.Subscriber: RoleConfig(
        description="Subscribed member of the channel",
        background_color="#a8e6cf",  # Light green
        text_color="#2c3e50",
        priority=70
    ),
    ChannelRole.Follower: RoleConfig(
        description="Follower of the channel",
        background_color="#dcedc8",  # Very light green
        text_color="#2c3e50",
        priority=60
    ),
    ChannelRole.Basic: RoleConfig(
        description="Basic channel member",
        background_color="#f5f5f5",  # Light gray
        text_color="#2c3e50",
        priority=50
    )
}


def get_role_config(role: Optional[str | ChannelRole]) -> RoleConfig:
    """Get role configuration for a given role (string or enum)."""
    if role is None:
        return RoleConfig(
            description="No special role",
            background_color="#ffffff",  # White
            text_color="#6c757d",       # Gray text
            priority=0
        )
    
    # Convert string to enum if needed
    if isinstance(role, str):
        try:
            role_enum = ChannelRole(role)
        except ValueError:
            return ROLE_CONFIGS[ChannelRole.Basic]
    else:
        role_enum = role
    
    return ROLE_CONFIGS.get(role_enum, ROLE_CONFIGS[ChannelRole.Basic])


def get_highest_role(roles: List[str | ChannelRole]) -> Optional[ChannelRole]:
    """Get the highest priority role from a list of roles."""
    if not roles:
        return None
    
    # Convert strings to enums
    role_enums = []
    for role in roles:
        if isinstance(role, str):
            try:
                role_enums.append(ChannelRole(role))
            except ValueError:
                continue
        else:
            role_enums.append(role)
    
    if not role_enums:
        return None
    
    return max(role_enums, key=lambda role: get_role_config(role).priority)


def role_to_string(role: ChannelRole) -> str:
    """Convert role enum to string for database storage."""
    return role.value


def string_to_role(role_str: str) -> ChannelRole:
    """Convert string from database to role enum."""
    return ChannelRole(role_str)

