
from flask_login import current_user # type: ignore
from flask import flash, redirect, url_for, render_template, send_from_directory
from functools import wraps
from typing import Callable, Any, TypeVar, cast
from flask import request, abort
from app.models.config import config
from app.models.db import PermissionType, Users

F = TypeVar("F", bound=Callable[..., Any])

def require_api_key(func: F) -> F:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        key: str | None = request.headers.get("X-API-Key")
        if key != config.api_key:
            abort(401, description="Invalid or missing API key.")
        return func(*args, **kwargs)
    return cast(F, wrapper)

def require_permission(
                      permissions: PermissionType | list[PermissionType] | None = None, 
                      require_broadcaster: bool = False,
                      require_moderator: bool = False,
                      require_logged_in: bool = True,
                      broadcaster_id_param: str | None = None,
                      check_banned: bool = True):
    """
    Decorator to check if a user has the required permissions to access a route.
    
    Args:
        permissions: Permission(s) required to access the route
        require_broadcaster: If True, user must be the broadcaster
        require_moderator: If True, user must be a moderator
        broadcaster_id_param: Name of the parameter containing the broadcaster ID
        check_banned: If True, check if the user is banned
        require_logged_in: If True, user must be logged in and cannot be anonymous
        
    Usage examples:
        @app.route('/admin')
        @require_permission(PermissionType.Admin)
        def admin_page():
            return 'Admin page'
            
        @app.route('/broadcaster/<int:broadcaster_id>')
        @require_permission(require_broadcaster=True, broadcaster_id_param='broadcaster_id')
        def broadcaster_page(broadcaster_id):
            return f'Broadcaster page for {broadcaster_id}'
            
        @app.route('/mod/<int:broadcaster_id>')
        @require_permission(require_moderator=True, broadcaster_id_param='broadcaster_id')
        def mod_page(broadcaster_id):
            return f'Mod page for {broadcaster_id}'
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
                if check_banned and current_user.banned:
                    return render_template('banned.html', user=current_user)
                    
                # Get broadcaster_id from parameters if needed
                broadcaster_id = None
                if broadcaster_id_param and broadcaster_id_param in kwargs:
                    broadcaster_id = kwargs[broadcaster_id_param]
                    
                # Check permissions
                has_access = False
                
                # Check specific permissions
                if permissions and current_user.has_permission(permissions):
                    has_access = True
                    
                # Check if user is the broadcaster
                if require_broadcaster and broadcaster_id:
                    if current_user.has_broadcaster_id(broadcaster_id):
                        has_access = True
                        
                # Check if user is a moderator
                if require_moderator and broadcaster_id:
                    if current_user.is_moderator(broadcaster_id):
                        has_access = True
                
                # If any permission check failed, deny access
                if not has_access and (require_broadcaster or require_moderator or permissions is not None):
                    flash('You do not have permission to access this page', 'error')
                    return render_template("unauthorized.html")
            return f(*args, **kwargs)
        return decorated_function
    return decorator