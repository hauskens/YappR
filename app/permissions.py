
from flask_login import current_user  # type: ignore
from flask import flash, redirect, url_for, render_template
from functools import wraps
from typing import Callable, Any, TypeVar, cast
from flask import request, abort
from app.models.config import config
from app.models.enums import PermissionType, ChannelRole
from app.models.user import Users, get_role_config
from app.services import UserService

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
        require_broadcaster: bool = False,
        require_moderator: bool = False,
        require_logged_in: bool = True,
        broadcaster_id_param: str = "broadcaster_id",
        channel_id_param: str = "channel_id",
        channel_roles: ChannelRole | list[ChannelRole] | None = None,
        minimum_role: ChannelRole | None = None):
    """
    Decorator to check if a user has the required permissions to access a route.

    Args:
        permissions: Global permission(s) required to access the route
        require_broadcaster: If True, user must be the broadcaster
        require_moderator: If True, user must be a moderator
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
        @require_permission(require_broadcaster=True, broadcaster_id_param='broadcaster_id')
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
                    
                
                channel_id = None
                if channel_id_param in kwargs:
                    channel_id = kwargs[channel_id_param]

                # Check permissions
                has_access = False

                # Check global permissions first (highest priority)
                if permissions and UserService.has_permission(current_user, permissions):
                    has_access = True

                # Check if user is the broadcaster
                if not has_access and require_broadcaster and broadcaster_id:
                    if UserService.has_broadcaster_id(current_user, broadcaster_id):
                        has_access = True

                # Check if user is a moderator (legacy support)
                if not has_access and require_moderator and broadcaster_id:
                    if UserService.is_moderator(current_user, broadcaster_id):
                        has_access = True

                # Check channel-specific permissions
                if not has_access and channel_id:
                    # Check if user is banned from this channel
                    if UserService.is_banned_from_channel(current_user, channel_id):
                        flash('You are banned from this channel', 'error')
                        return render_template("banned.html", action="channel_banned", reason="Banned from this channel")
                    
                    user_role = UserService.get_channel_role(current_user, channel_id)
                    
                    # Check specific channel roles
                    if channel_roles and user_role:
                        if isinstance(channel_roles, ChannelRole):
                            required_roles = [channel_roles]
                        else:
                            required_roles = channel_roles
                        
                        if user_role in required_roles:
                            has_access = True
                    
                    # Check minimum role requirement
                    if not has_access and minimum_role and user_role:
                        user_priority = get_role_config(user_role).priority
                        min_priority = get_role_config(minimum_role).priority
                        
                        if user_priority >= min_priority:
                            has_access = True

                # Determine if access should be checked
                requires_check = (require_broadcaster or require_moderator or 
                                permissions is not None or channel_roles is not None or 
                                minimum_role is not None)

                # If any permission check was required but failed, deny access
                if not has_access and requires_check:
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
