from sqlalchemy import String, Integer, Boolean, ForeignKey, DateTime, Text, Enum, Float, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from .base import Base
from .enums import AccountSource
from flask_login import UserMixin  # type: ignore


class Users(Base, UserMixin):
    __tablename__: str = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(500))
    external_account_id: Mapped[str | None] = mapped_column(
        String(500), unique=True, nullable=True
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
    permissions: Mapped[list["Permissions"]] = relationship(  # type: ignore[name-defined]
        back_populates="user", cascade="all, delete-orphan"
    )
    channel_moderators: Mapped[list["ChannelModerator"]] = relationship(  # type: ignore[name-defined]
        back_populates="user", cascade="all, delete-orphan"
    )
    oauth: Mapped[list["OAuth"]] = relationship(  # type: ignore[name-defined]
        back_populates="user", cascade="all, delete-orphan"
    )

#     def has_permission(
#         self, permissions: PermissionType | str | Iterable[PermissionType | str]
#     ) -> bool:
#         if isinstance(permissions, (PermissionType, str)):
#             permissions = [permissions]

#         permission_types: list[PermissionType] = [
#             PermissionType(perm) if isinstance(perm, str) else perm
#             for perm in permissions
#         ]

#         if self.banned_reason is None:
#             return any(p.permission_type in permission_types for p in self.permissions)
#         return False

#     def has_broadcaster_id(self, broadcaster_id: int) -> bool:
#         return db.session.execute(
#             select(Broadcaster)
#             .join(Broadcaster.channels)
#             .where(Channels.platform_channel_id == self.external_account_id, Broadcaster.id == broadcaster_id)
#             .limit(1)
#         ).scalars().one_or_none() is not None

#     def is_moderator(self, broadcaster_id: int | None = None) -> bool:
#         if broadcaster_id is None:
#             return db.session.query(ChannelModerator).filter_by(user_id=self.id).one_or_none() is not None
#         else:
#             return db.session.query(ChannelModerator).filter_by(user_id=self.id, channel_id=broadcaster_id).one_or_none() is not None

#     def is_broadcaster(self) -> bool:
#         return db.session.execute(
#             select(Broadcaster)
#             .join(Broadcaster.channels)
#             .where(Channels.platform_channel_id == self.external_account_id)
#             .limit(1)
#         ).scalars().one_or_none() is not None

#     def get_broadcaster(self) -> Broadcaster | None:
#         return db.session.execute(
#             select(Broadcaster)
#             .join(Broadcaster.channels)
#             .where(Channels.platform_channel_id == self.external_account_id)
#             .limit(1)
#         ).scalars().one_or_none()

#     def add_permissions(self, permission_type: PermissionType):
#         if not self.has_permission(permission_type):
#             db.session.add(
#                 Permissions(user_id=self.id, permission_type=permission_type)
#             )
#             db.session.commit()
#             logger.info(f"Granted {permission_type.name} to {self.name}!")

#     def update_moderated_channels(self) -> list[TwitchChannelModerator]:
#         if self.account_type == AccountSource.Twitch:
#             try:
#                 oauth = db.session.query(OAuth).filter_by(
#                     user_id=self.id).one_or_none()
#                 if oauth is None:
#                     return []
#                 moderated_channels = asyncio.run(get_moderated_channels(
#                     self.external_account_id, user_token=oauth.token["access_token"], refresh_token=oauth.token["refresh_token"]))
#                 if moderated_channels is None:
#                     return []

#                 logger.info(f"Updating moderated channels for {self.name}")

#                 # Get existing channel moderator entries for this user
#                 existing_moderators = db.session.query(
#                     ChannelModerator).filter_by(user_id=self.id).all()
#                 existing_moderator_channel_ids = set()
#                 found_channel_ids = set()

#                 # Process channels from Twitch API
#                 for channel in moderated_channels:
#                     logger.info(
#                         f"Updating channel {channel.broadcaster_id} - {channel.broadcaster_name}")
#                     existing_channel = db.session.query(Channels).filter_by(
#                         platform_channel_id=channel.broadcaster_id).one_or_none()

#                     if existing_channel is not None:
#                         found_channel_ids.add(existing_channel.id)
#                         # Check if this moderator relationship already exists
#                         existing_mod = db.session.query(ChannelModerator).filter_by(
#                             user_id=self.id,
#                             channel_id=existing_channel.id
#                         ).one_or_none()

#                         if existing_mod is None:
#                             # Add new moderator relationship
#                             db.session.add(
#                                 ChannelModerator(
#                                     user_id=self.id, channel_id=existing_channel.id)
#                             )

#                 # Get all existing channel IDs for this user's moderator entries
#                 for mod in existing_moderators:
#                     existing_moderator_channel_ids.add(mod.channel_id)

#                 # Delete moderator entries that weren't found in the Twitch API response
#                 channels_to_remove = existing_moderator_channel_ids - found_channel_ids
#                 if channels_to_remove:
#                     logger.info(
#                         f"Removing {len(channels_to_remove)} channel moderator entries for {self.name}")

#                     db.session.query(ChannelModerator).filter(
#                         ChannelModerator.user_id == self.id,
#                         ChannelModerator.channel_id.in_(channels_to_remove)
#                     ).delete(synchronize_session=False)

#                 db.session.commit()
#                 return [channel for channel in moderated_channels]
#             except Exception as e:
#                 logger.error(
#                     f"Failed to update moderated channels for {self.name}: {e}")
#                 return []
#         else:
#             return []

#     def get_twitch_account_type(self) -> Literal["partner", "affiliate", "regular"]:
#         if self.account_type == AccountSource.Twitch:
#             if config.debug == True and config.debug_broadcaster_id is not None and self.external_account_id == str(config.debug_broadcaster_id):
#                 return "partner"
#             user = asyncio.run(get_twitch_user_by_id(self.external_account_id))
#             logger.info(user.broadcaster_type)
#             if user.id == self.external_account_id:
#                 return user.broadcaster_type
#         return "regular"


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
    submissions: Mapped[list["ContentQueueSubmission"]  # type: ignore[name-defined]
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
    broadcaster: Mapped["Broadcaster"] = relationship() # type: ignore[name-defined]
    banned: Mapped[bool] = mapped_column(Boolean, default=False)
    banned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    unban_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
