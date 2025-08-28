"""
Moderation service for handling moderation-related business logic.
"""
from datetime import datetime, timedelta
from typing import Sequence

from sqlalchemy import select, or_, and_
from app.models import db
from app.models import Users, ContentQueue, ContentQueueSubmission
from app.models.user import ModerationAction
from app.models.enums import ModerationActionType, ModerationScope, ChannelRole, PermissionType
from app.logger import logger
from app.services.user import UserService


class ModerationService:
    """Service class for moderation-related operations."""

    @staticmethod
    def ban_user(target_user_id: int, scope: ModerationScope, reason: str, 
                issued_by_user_id: int, channel_id: int | None = None, 
                duration_seconds: int | None = None) -> ModerationAction:
        """Ban a user globally or from a specific channel."""
        # Check permissions
        moderator = db.session.get(Users, issued_by_user_id)
        target_user = db.session.get(Users, target_user_id)
        
        if not moderator or not target_user:
            raise ValueError("Invalid user IDs provided")

        if channel_id and not UserService.has_permission(moderator, PermissionType.Admin):
            raise PermissionError("Insufficient permissions to ban this user from a specific channel, cannot ban admins")
        
        if not ModerationService.check_moderation_permissions(moderator, target_user, channel_id):
            raise PermissionError("Insufficient permissions to ban this user")
        
        expires_at = None
        if duration_seconds:
            expires_at = datetime.now() + timedelta(seconds=duration_seconds)
        
        action = ModerationAction(
            target_user_id=target_user_id,
            action_type=ModerationActionType.ban.value,
            scope=scope.value,
            channel_id=channel_id,
            reason=reason,
            duration_seconds=duration_seconds,
            expires_at=expires_at,
            issued_by=issued_by_user_id
        )
        
        db.session.add(action)
        
        # Update user's global ban status if global scope
        if scope == ModerationScope.global_:
            target_user.globally_banned = True
            target_user.global_ban_reason = reason
            target_user.global_ban_expires_at = expires_at
        
        db.session.commit()
        logger.info(f"Banned user {target_user_id} ({scope.value}) by user {issued_by_user_id}: {reason}")
        return action

    @staticmethod
    def timeout_user(target_user_id: int, channel_id: int, reason: str,
                    issued_by_user_id: int, duration_seconds: int) -> ModerationAction:
        """Timeout a user in a specific channel."""
        # Check permissions
        moderator = db.session.get(Users, issued_by_user_id)
        target_user = db.session.get(Users, target_user_id)
        
        if not moderator or not target_user:
            raise ValueError("Invalid user IDs provided")
        
        if UserService.has_permission(target_user, PermissionType.Admin):
            raise PermissionError("Insufficient permissions to timeout this user, cannot timeout admins")
            

        if not ModerationService.check_moderation_permissions(moderator, target_user, channel_id):
            raise PermissionError("Insufficient permissions to timeout this user")
        
        expires_at = datetime.now() + timedelta(seconds=duration_seconds)
        
        action = ModerationAction(
            target_user_id=target_user_id,
            action_type=ModerationActionType.timeout.value,
            scope=ModerationScope.channel.value,
            channel_id=channel_id,
            reason=reason,
            duration_seconds=duration_seconds,
            expires_at=expires_at,
            issued_by=issued_by_user_id
        )
        
        db.session.add(action)
        db.session.commit()
        logger.info(f"Timeout user {target_user_id} in channel {channel_id} for {duration_seconds}s by user {issued_by_user_id}: {reason}")
        return action

    @staticmethod
    def warn_user(target_user_id: int, reason: str, issued_by_user_id: int, 
                 channel_id: int | None = None) -> ModerationAction:
        """Issue a warning to a user."""
        # Check permissions
        moderator = db.session.get(Users, issued_by_user_id)
        target_user = db.session.get(Users, target_user_id)
        
        if not moderator or not target_user:
            raise ValueError("Invalid user IDs provided")
        
        if not ModerationService.check_moderation_permissions(moderator, target_user, channel_id):
            raise PermissionError("Insufficient permissions to warn this user")
        
        scope = ModerationScope.channel if channel_id else ModerationScope.global_
        
        action = ModerationAction(
            target_user_id=target_user_id,
            action_type=ModerationActionType.warning.value,
            scope=scope.value,
            channel_id=channel_id,
            reason=reason,
            issued_by=issued_by_user_id
        )
        
        db.session.add(action)
        db.session.commit()
        logger.info(f"Warning issued to user {target_user_id} ({scope.value}) by user {issued_by_user_id}: {reason}")
        return action

    @staticmethod
    def revoke_moderation_action(action_id: int, revoked_by_user_id: int, reason: str = "") -> bool:
        """Revoke a moderation action."""
        action = db.session.get(ModerationAction, action_id)
        if not action or not action.active:
            return False
        
        action.active = False
        action.revoked_at = datetime.now()
        action.revoked_by = revoked_by_user_id
        action.revoked_reason = reason
        
        # If this was a global ban, update the user's global ban status
        if (action.action_type == ModerationActionType.ban.value and 
            action.scope == ModerationScope.global_.value):
            target_user = db.session.get(Users, action.target_user_id)
            if target_user:
                target_user.globally_banned = False
                target_user.global_ban_reason = None
                target_user.global_ban_expires_at = None
        
        db.session.commit()
        logger.info(f"Revoked moderation action {action_id} by user {revoked_by_user_id}: {reason}")
        return True

    @staticmethod
    def unban_user(target_user_id: int, issued_by_user_id: int, reason: str = "",
                  channel_id: int | None = None) -> ModerationAction | None:
        """Unban a user by creating an unban action and revoking active bans."""
        # Check permissions
        moderator = db.session.get(Users, issued_by_user_id)
        target_user = db.session.get(Users, target_user_id)
        
        if not moderator or not target_user:
            raise ValueError("Invalid user IDs provided")
        
        if not ModerationService.check_moderation_permissions(moderator, target_user, channel_id):
            raise PermissionError("Insufficient permissions to unban this user")
        
        # Find active ban(s) to revoke
        scope = ModerationScope.channel if channel_id else ModerationScope.global_
        
        query = select(ModerationAction).where(
            ModerationAction.target_user_id == target_user_id,
            ModerationAction.action_type == ModerationActionType.ban.value,
            ModerationAction.scope == scope.value,
            ModerationAction.active == True
        )
        
        if channel_id:
            query = query.where(ModerationAction.channel_id == channel_id)
        
        active_bans = db.session.execute(query).scalars().all()
        
        if not active_bans:
            return None
        
        # Create unban action
        unban_action = ModerationAction(
            target_user_id=target_user_id,
            action_type=ModerationActionType.unban.value,
            scope=scope.value,
            channel_id=channel_id,
            reason=reason or "Unbanned",
            issued_by=issued_by_user_id
        )
        
        db.session.add(unban_action)
        
        # Revoke active bans
        for ban in active_bans:
            ban.active = False
            ban.revoked_at = datetime.now()
            ban.revoked_by = issued_by_user_id
            ban.revoked_reason = f"Unbanned: {reason}"
        
        # Update global ban status if global unban
        if scope == ModerationScope.global_:
            target_user.globally_banned = False
            target_user.global_ban_reason = None
            target_user.global_ban_expires_at = None
        
        db.session.commit()
        logger.info(f"Unbanned user {target_user_id} ({scope.value}) by user {issued_by_user_id}: {reason}")
        return unban_action

    @staticmethod
    def get_user_moderation_history(target_user_id: int, 
                                   channel_id: int | None = None,
                                   action_type: ModerationActionType | None = None,
                                   include_inactive: bool = True) -> Sequence[ModerationAction]:
        """Get moderation history for a user."""
        query = select(ModerationAction).where(
            ModerationAction.target_user_id == target_user_id
        )
        
        if not include_inactive:
            query = query.where(ModerationAction.active == True)
        
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
        
        if action_type is not None:
            query = query.where(ModerationAction.action_type == action_type)
        
        query = query.order_by(ModerationAction.issued_at.desc())
        
        return db.session.execute(query).scalars().all()

    @staticmethod
    def get_channel_moderation_actions(channel_id: int, 
                                     action_type: ModerationActionType | None = None,
                                     include_inactive: bool = False,
                                     limit: int = 100) -> Sequence[ModerationAction]:
        """Get recent moderation actions for a channel."""
        query = select(ModerationAction).where(
            or_(
                ModerationAction.scope == ModerationScope.global_,
                and_(
                    ModerationAction.scope == ModerationScope.channel,
                    ModerationAction.channel_id == channel_id
                )
            )
        )
        
        if not include_inactive:
            query = query.where(ModerationAction.active == True)
        
        if action_type is not None:
            query = query.where(ModerationAction.action_type == action_type)
        
        query = query.order_by(ModerationAction.issued_at.desc()).limit(limit)
        
        return db.session.execute(query).scalars().all()

    @staticmethod
    def check_moderation_permissions(moderator_user: Users, target_user: Users, 
                                   channel_id: int | None = None) -> bool:
        """Check if a moderator has permission to moderate a target user."""
        from app.services.user import UserService
        
        # Global admins can moderate anyone
        if UserService.has_permission(moderator_user, "admin"):
            return True
        
        # Channel-specific moderation
        if channel_id:
            moderator_role = UserService.get_channel_role(moderator_user, channel_id)
            target_role = UserService.get_channel_role(target_user, channel_id)
            
            # Channel owners can moderate anyone in their channel
            if moderator_role == ChannelRole.Owner:
                return True
            
            # Mods can moderate subscribers, followers, basic users, and users with no role
            if moderator_role == ChannelRole.Mod:
                return target_role in [ChannelRole.Subscriber, ChannelRole.Follower, ChannelRole.Basic, None]
        
        return False

    @staticmethod
    def cleanup_expired_actions() -> int:
        """Clean up expired moderation actions. Returns count of cleaned up actions."""
        expired_actions = db.session.execute(
            select(ModerationAction).where(
                ModerationAction.active == True,
                ModerationAction.expires_at.is_not(None),
                ModerationAction.expires_at <= datetime.now()
            )
        ).scalars().all()
        
        count = 0
        for action in expired_actions:
            action.active = False
            
            # If this was a global ban, update the user's global ban status
            if (action.action_type == ModerationActionType.ban and 
                action.scope == ModerationScope.global_):
                target_user = db.session.get(Users, action.target_user_id)
                if target_user and target_user.globally_banned:
                    target_user.globally_banned = False
                    target_user.global_ban_reason = None
                    target_user.global_ban_expires_at = None
            
            count += 1
        
        if count > 0:
            db.session.commit()
            logger.info(f"Cleaned up {count} expired moderation actions")
        
        return count

    @staticmethod
    def get_banned_channel_ids(user: Users) -> list[int]:
        return [channel_id for channel_id in db.session.execute(
            select(ModerationAction.channel_id)
            .where(ModerationAction.target_user_id == user.id, ModerationAction.active == True, ModerationAction.scope == ModerationScope.channel.value, ModerationAction.action_type == ModerationActionType.ban.value)
        ).scalars().all() if channel_id is not None]

    @staticmethod
    def record_external_moderation_event(target_user_id: int, action_type: ModerationActionType,
                                        channel_id: int, reason: str, duration_seconds: int | None = None,
                                        issued_by_user_id: int | None = None) -> ModerationAction:
        """Record a moderation event from external source (like Twitch chat events)."""
        expires_at = None
        if duration_seconds:
            expires_at = datetime.now() + timedelta(seconds=duration_seconds)
        
        action = ModerationAction(
            target_user_id=target_user_id,
            action_type=action_type.value,
            scope=ModerationScope.channel.value,
            channel_id=channel_id,
            reason=reason,
            duration_seconds=duration_seconds,
            expires_at=expires_at,
            issued_by=issued_by_user_id
        )
        
        db.session.add(action)
        
        # Clean up content queue entries for this user
        ModerationService.cleanup_user_content_queue_entries(
            target_user_id, channel_id, action_type, duration_seconds
        )
        
        db.session.commit()
        logger.info(f"Recorded external {action_type.value} for user {target_user_id} in channel {channel_id}: {reason}")
        return action

    @staticmethod
    def cleanup_user_content_queue_entries(target_user_id: int, channel_id: int, 
                                         action_type: ModerationActionType, 
                                         duration_seconds: int | None = None) -> int:
        """Clean up content queue entries for moderated users."""
        from app.models.channel import Channels
        from app.services.broadcaster import BroadcasterService
        
        # Get the broadcaster for this channel
        channel = db.session.get(Channels, channel_id)
        if not channel:
            logger.warning(f"Channel {channel_id} not found for content queue cleanup")
            return 0
        
        broadcaster = BroadcasterService.get_by_internal_channel_id(channel_id)
        if not broadcaster:
            logger.warning(f"Broadcaster not found for channel {channel_id}")
            return 0
        
        count = 0
        
        if action_type == ModerationActionType.ban:
            # For bans, remove all unwatched/unskipped entries
            entries_to_delete = db.session.execute(
                select(ContentQueue)
                .join(ContentQueueSubmission, ContentQueue.id == ContentQueueSubmission.content_queue_id)
                .where(
                    ContentQueueSubmission.user_id == target_user_id,
                    ContentQueue.broadcaster_id == broadcaster.id,
                    ContentQueue.watched == False,
                    ContentQueue.skipped == False
                )
            ).scalars().all()
            
            for entry in entries_to_delete:
                db.session.delete(entry)
                count += 1
            
            logger.info(f"Cleaned up {count} content queue entries for banned user {target_user_id}")
            
        elif action_type == ModerationActionType.timeout and duration_seconds:
            # For timeouts, remove entries from the past X hours
            cutoff_time = datetime.now() - timedelta(seconds=duration_seconds)
            
            entries_to_delete = db.session.execute(
                select(ContentQueue)
                .join(ContentQueueSubmission, ContentQueue.id == ContentQueueSubmission.content_queue_id)
                .where(
                    ContentQueueSubmission.user_id == target_user_id,
                    ContentQueue.broadcaster_id == broadcaster.id,
                    ContentQueue.watched == False,
                    ContentQueue.skipped == False,
                    ContentQueueSubmission.submitted_at >= cutoff_time
                )
            ).scalars().all()
            
            for entry in entries_to_delete:
                db.session.delete(entry)
                count += 1
            
            logger.info(f"Cleaned up {count} content queue entries for timed out user {target_user_id} (past {duration_seconds}s)")
        
        return count

    @staticmethod
    def can_submit_content(user_id: int, channel_id: int) -> bool:
        """Check if user can submit content to a channel (not banned or timed out)."""
        from app.services.user import UserService
        from app.services.broadcaster import BroadcasterService
        
        user = db.session.get(Users, user_id)
        if not user:
            return False
        
        # Check global ban
        if UserService.is_globally_banned(user):
            return False
        
        # Get broadcaster for channel
        broadcaster = BroadcasterService.get_by_internal_channel_id(channel_id)
        if not broadcaster:
            return True  # If broadcaster not found, allow submission
        
        # Check channel-specific ban
        if UserService.is_banned_from_channel(user, channel_id):
            return False
        
        # Check for active timeout
        active_timeout = db.session.execute(
            select(ModerationAction)
            .where(
                ModerationAction.target_user_id == user_id,
                ModerationAction.action_type == ModerationActionType.timeout.value,
                ModerationAction.scope == ModerationScope.channel.value,
                ModerationAction.channel_id == channel_id,
                ModerationAction.active == True,
                or_(
                    ModerationAction.expires_at.is_(None),
                    ModerationAction.expires_at > datetime.now()
                )
            )
        ).scalar_one_or_none()
        
        return active_timeout is None

# For template accessibility, create simple function interfaces
def ban_user_globally(target_user_id: int, reason: str, issued_by_user_id: int, 
                     duration_seconds: int | None = None) -> ModerationAction:
    """Ban a user globally for use in templates."""
    return ModerationService.ban_user(
        target_user_id, ModerationScope.global_, reason, issued_by_user_id, 
        duration_seconds=duration_seconds
    )


def ban_user_from_channel(target_user_id: int, channel_id: int, reason: str, 
                         issued_by_user_id: int, duration_seconds: int | None = None) -> ModerationAction:
    """Ban a user from a channel for use in templates."""
    return ModerationService.ban_user(
        target_user_id, ModerationScope.channel, reason, issued_by_user_id, 
        channel_id=channel_id, duration_seconds=duration_seconds
    )


def check_user_banned(user: Users, channel_id: int | None = None) -> bool:
    """Check if user is globally banned or banned from a channel for use in templates."""
    from app.services.user import UserService
    
    if UserService.is_globally_banned(user):
        return True
    
    if channel_id and UserService.is_banned_from_channel(user, channel_id):
        return True
    
    return False