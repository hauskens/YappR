
from flask_login import current_user  # type: ignore
from flask import flash, redirect, url_for, render_template
from functools import wraps
from typing import Callable, Any, TypeVar, cast
from flask import request, abort
from app.models.config import config
from app.models.enums import PermissionType, ChannelRole
from app.models.user import Users, get_role_config
from app.services import UserService, BroadcasterService, ModerationService
from app.logger import logger

F = TypeVar("F", bound=Callable[..., Any])


def require_api_key(func: F) -> F:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        key: str | None = request.headers.get("X-API-Key")
        if key != config.api_key:
            abort(401, description="Invalid or missing API key.")
        return func(*args, **kwargs)
    return cast(F, wrapper)

def check_banned():
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args: Any, **kwargs: Any) -> Any:
            if isinstance(current_user, Users) and not current_user.is_anonymous:
                if current_user.globally_banned:
                    return render_template('banned.html', action="banned", reason=current_user.global_ban_reason, until=current_user.global_ban_expires_at)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_permission(
        permissions: PermissionType | list[PermissionType] | None = None,
        check_broadcaster: bool = False,
        check_moderator: bool = False,
        check_anyone: bool = False,
        require_logged_in: bool = True,
        broadcaster_id_param: str = "broadcaster_id",
        channel_id_param: str = "channel_id",
        channel_roles: ChannelRole | list[ChannelRole] | None = None,
        minimum_role: ChannelRole | None = None):
    """
    Decorator to check if a user has the required permissions to access a route.

    Args:
        permissions: Global permission(s) required to access the route
        check_broadcaster: If True, allows user to access route if they are broadcaster
        check_moderator: If True, allows user to access route if they are moderator
        check_anyone: If True, allows any authenticated user to access route
        require_logged_in: If True, user must be logged in and cannot be anonymous
        broadcaster_id_param: Name of the parameter containing the broadcaster ID
        channel_id_param: Name of the parameter containing the channel ID
        channel_roles: Specific channel role(s) required to access the route
        minimum_role: Minimum channel role required (inclusive of higher roles)

    Usage examples:
        @app.route('/admin')
        @require_permission(permissions=PermissionType.Admin)
        def admin_page():
            return 'Admin page'

        @app.route('/channel/<int:channel_id>/moderate')
        @require_permission(channel_id_param='channel_id', channel_roles=[ChannelRole.Owner, ChannelRole.Mod])
        def moderate_channel(channel_id):
            return f'Moderate channel {channel_id}'
            
        @app.route('/channel/<int:channel_id>/vip-area')
        @require_permission(channel_id_param='channel_id', minimum_role=ChannelRole.VIP)
        def vip_area(channel_id):
            return f'VIP area for channel {channel_id}'

        @app.route('/broadcaster/<int:broadcaster_id>')
        @require_permission(check_broadcaster=True, broadcaster_id_param='broadcaster_id')
        def broadcaster_page(broadcaster_id):
            return f'Broadcaster page for {broadcaster_id}'
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args: Any, **kwargs: Any) -> Any:
            # Check if user is logged in
            if require_logged_in and current_user.is_anonymous:
                flash('You must be logged in to access this page', 'error')
                return redirect(url_for('root.login'))

            if isinstance(current_user, Users):
                # Check if user is banned
                if current_user.globally_banned:
                    return render_template('banned.html', action="banned", reason=current_user.global_ban_reason, until=current_user.global_ban_expires_at)

                # Get broadcaster_id and channel_id from parameters if needed
                broadcaster_id = None
                if broadcaster_id_param in kwargs:
                    broadcaster_id = kwargs[broadcaster_id_param]
                    channel_ids = [ channel.id for channel in BroadcasterService.get_channels(broadcaster_id=broadcaster_id)]
                    if any(channel_id in ModerationService.get_banned_channel_ids(current_user) for channel_id in channel_ids):
                        logger.info("User %s is banned from broadcaster %s", current_user, broadcaster_id)
                        return render_template('banned.html', action="banned from this broadcaster", reason="Banned from this broadcaster")

                channel_id = None
                if channel_id_param in kwargs:
                    channel_id = kwargs[channel_id_param]
                    broadcaster_id = BroadcasterService.get_by_internal_channel_id(channel_id)
                    logger.info("Checking if channel %s is banned for user %s", channel_id, current_user)
                    if channel_id in ModerationService.get_banned_channel_ids(current_user):
                        return render_template('banned.html', action="banned from this channel", reason="Banned from this channel")



                has_permission = check_permission(user=current_user, permissions=permissions, check_broadcaster=check_broadcaster, check_moderator=check_moderator, check_anyone=check_anyone, require_logged_in=require_logged_in, broadcaster_id=broadcaster_id, channel_id=channel_id, channel_roles=channel_roles, minimum_role=minimum_role)

                # Determine if access should be checked
                requires_check = (check_broadcaster or check_moderator or 
                                permissions is not None or channel_roles is not None or 
                                minimum_role is not None)

                # If any permission check was required but failed, deny access
                if requires_check and not has_permission:
                    return render_template("errors/401.html")
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_channel_role(
        channel_id_param: str,
        roles: ChannelRole | list[ChannelRole] | None = None,
        minimum_role: ChannelRole | None = None):
    """
    Convenience decorator for channel-specific role requirements.
    
    Args:
        channel_id_param: Name of the parameter containing the channel ID
        roles: Specific role(s) required
        minimum_role: Minimum role required (inclusive of higher roles)
    
    Usage examples:
        @app.route('/channel/<int:channel_id>/moderate')
        @require_channel_role('channel_id', roles=[ChannelRole.Owner, ChannelRole.Mod])
        def moderate_channel(channel_id):
            return f'Moderate channel {channel_id}'
            
        @app.route('/channel/<int:channel_id>/vip-area')
        @require_channel_role('channel_id', minimum_role=ChannelRole.VIP)
        def vip_area(channel_id):
            return f'VIP area for channel {channel_id}'
    """
    return require_permission(
        channel_id_param=channel_id_param,
        channel_roles=roles,
        minimum_role=minimum_role
    )

def check_permission(
        user: Users,
        permissions: PermissionType | list[PermissionType] | None = None,
        check_broadcaster: bool = False,
        check_moderator: bool = False,
        check_anyone: bool = False,
        require_logged_in: bool = True,
        broadcaster_id: int | None = None,
        channel_id: int | None = None,
        channel_roles: ChannelRole | list[ChannelRole] | None = None,
        minimum_role: ChannelRole | None = None):
    
    if user.is_anonymous:
        return False
    # Check if user is banned
    if user.globally_banned:
        return False

    # Get broadcaster_id and channel_id from parameters if needed
    if broadcaster_id is not None:
        channel_ids = [ channel.id for channel in BroadcasterService.get_channels(broadcaster_id=broadcaster_id)]
        if any(channel_id in ModerationService.get_banned_channel_ids(user) for channel_id in channel_ids):
            logger.info("User %s is banned from broadcaster %s", user, broadcaster_id)
            return False

    if channel_id is not None:
        broadcaster = BroadcasterService.get_by_internal_channel_id(channel_id)
        if broadcaster is None:
            raise ValueError(f"Channel {channel_id} not found")
        logger.info("Checking if channel %s is banned for user %s", channel_id, user)
        if any(channel_id in ModerationService.get_banned_channel_ids(user) for channel_id in broadcaster.channels):
            logger.info("User %s is banned from channel %s", user, broadcaster_id)
            return False

    # Check permissions
    if check_anyone:
        return True

    if UserService.is_admin(current_user):
        return True
    # Check global permissions first (highest priority)
    if permissions and UserService.has_permission(current_user, permissions):
        return True

    # Check if user is the broadcaster
    if check_broadcaster and broadcaster_id:
        if UserService.has_broadcaster_id(current_user, broadcaster_id):
            return True

    # Check if user is a moderator (legacy support)
    if check_moderator and broadcaster_id:
        if UserService.is_moderator(current_user, broadcaster_id):
            return True

    # Check channel-specific permissions
    if channel_id:
        user_role = UserService.get_channel_role(current_user, channel_id)
        
        # Check specific channel roles
        if channel_roles and user_role:
            if isinstance(channel_roles, ChannelRole):
                required_roles = [channel_roles]
            else:
                required_roles = channel_roles
            
            if user_role in required_roles:
                return True
        
        # Check minimum role requirement
        if minimum_role and user_role:
            user_priority = get_role_config(user_role).priority
            min_priority = get_role_config(minimum_role).priority
            
            if user_priority >= min_priority:
                return True

