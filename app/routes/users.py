from flask import Blueprint, render_template, request, redirect, jsonify, flash
from flask_login import current_user, login_required  # type: ignore
from app.permissions import require_permission
from app.models import db
from app.models import ExternalUser, ExternalUserWeight, ContentQueueSubmission, PermissionType, Users, Channels
from app.models.user import get_role_config, get_highest_role
from app.models.enums import ChannelRole, ModerationActionType, ModerationScope
from app.logger import logger
from app.services import BroadcasterService, UserService
from app.services.moderation import ModerationService
from sqlalchemy import select, or_
from datetime import datetime

users_blueprint = Blueprint('users', __name__, url_prefix='/users',
                            template_folder='templates', static_folder='static')


@users_blueprint.route("/")
@login_required
@require_permission(permissions=PermissionType.Admin)
def list_users():
    """Main users listing page."""
    search = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    query = db.session.query(Users)
    
    if search:
        query = query.filter(
            or_(
                Users.name.ilike(f'%{search}%'),
                Users.external_account_id.ilike(f'%{search}%')
            )
        )
    
    users_paginated = query.paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    channels = db.session.query(Channels).all()
    
    return render_template(
        "users.html",
        users=users_paginated.items,
        pagination=users_paginated,
        search=search,
        channels=channels,
        channel_roles=ChannelRole,
        get_role_config=get_role_config
    )


@users_blueprint.route("/search")
@login_required
@require_permission(permissions=PermissionType.Admin)
def search_users():
    """HTMX endpoint for user search."""
    search = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    query = db.session.query(Users)
    
    if search:
        query = query.filter(
            or_(
                Users.name.ilike(f'%{search}%'),
                Users.external_account_id.ilike(f'%{search}%')
            )
        )
    
    users_paginated = query.paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template(
        "components/users_table.html",
        users=users_paginated.items,
        pagination=users_paginated,
        search=search,
        get_role_config=get_role_config
    )


@users_blueprint.route("/roles", methods=["POST"])
@login_required
@require_permission(permissions=PermissionType.Admin)
def grant_role():
    """Grant a channel role to a user."""
    user_id = request.form.get('user_id', type=int)
    channel_id = request.form.get('channel_id', type=int)
    role_name = request.form.get('role')
    
    try:
        role = ChannelRole(role_name)
        UserService.grant_channel_role(
            user_id=user_id,
            channel_id=channel_id,
            role=role,
            granted_by_user_id=current_user.id
        )
        
        user = db.session.get(Users, user_id)
        channel = db.session.get(Channels, channel_id)
        
        return render_template(
            "components/user_roles.html",
            user=user,
            channel=channel,
            get_role_config=get_role_config
        )
    except Exception as e:
        logger.error(f"Error granting role: {e}")
        return f"<div class='text-danger'>Error: {str(e)}</div>", 400


@users_blueprint.route("/<int:user_id>/roles/<int:channel_id>", methods=["DELETE"])
@login_required
@require_permission(permissions=PermissionType.Admin)
def revoke_role(user_id: int, channel_id: int):
    """Revoke a channel role from a user."""
    try:
        UserService.revoke_channel_role(user_id, channel_id)
        
        user = db.session.get(Users, user_id)
        channel = db.session.get(Channels, channel_id)
        
        return render_template(
            "components/user_roles.html",
            user=user,
            channel=channel,
            get_role_config=get_role_config
        )
    except Exception as e:
        logger.error(f"Error revoking role: {e}")
        return f"<div class='text-danger'>Error: {str(e)}</div>", 400


@users_blueprint.route("/<int:user_id>/ban", methods=["POST"])
@login_required
@require_permission(permissions=PermissionType.Admin)
def ban_user(user_id: int):
    """Ban a user globally or from a specific channel."""
    scope_str = request.form.get('scope', 'global')
    channel_id = request.form.get('channel_id', type=int)
    reason = request.form.get('reason', 'No reason provided')
    duration_hours = request.form.get('duration_hours', type=int)
    
    try:
        scope = ModerationScope.global_ if scope_str == 'global' else ModerationScope.channel
        duration_seconds = duration_hours * 3600 if duration_hours else None
        
        ModerationService.ban_user(
            target_user_id=user_id,
            scope=scope,
            reason=reason,
            issued_by_user_id=current_user.id,
            channel_id=channel_id if scope == ModerationScope.channel else None,
            duration_seconds=duration_seconds
        )
        
        return render_template(
            "components/user_moderation_status.html",
            user=db.session.get(Users, user_id)
        )
    except Exception as e:
        logger.error(f"Error banning user: {e}")
        return f"<div class='text-danger'>Error: {str(e)}</div>", 400


@users_blueprint.route("/<int:user_id>/unban", methods=["POST"])
@login_required
@require_permission(permissions=PermissionType.Admin)
def unban_user(user_id: int):
    """Unban a user."""
    channel_id = request.form.get('channel_id', type=int)
    reason = request.form.get('reason', 'Unbanned by admin')
    
    try:
        ModerationService.unban_user(
            target_user_id=user_id,
            issued_by_user_id=current_user.id,
            reason=reason,
            channel_id=channel_id
        )
        
        return render_template(
            "components/user_moderation_status.html",
            user=db.session.get(Users, user_id)
        )
    except Exception as e:
        logger.error(f"Error unbanning user: {e}")
        return f"<div class='text-danger'>Error: {str(e)}</div>", 400


@users_blueprint.route("/<int:user_id>/moderation-history")
@login_required
@require_permission(permissions=PermissionType.Admin)
def moderation_history(user_id: int):
    """Get moderation history for a user."""
    channel_id = request.args.get('channel_id', type=int)
    
    history = ModerationService.get_user_moderation_history(
        target_user_id=user_id,
        channel_id=channel_id,
        include_inactive=True
    )
    
    return render_template(
        "components/moderation_history.html",
        history=history,
        user=db.session.get(Users, user_id),
        ModerationActionType=ModerationActionType,
        ModerationScope=ModerationScope,
        current_time=datetime.now()
    )


@users_blueprint.route("/<int:user_id>/ban-modal")
@login_required
@require_permission(permissions=PermissionType.Admin)
def ban_modal(user_id: int):
    """Get ban modal content."""
    user = db.session.get(Users, user_id)
    channels = db.session.query(Channels).all()
    
    return render_template(
        "components/ban_modal.html",
        user=user,
        channels=channels
    )


@users_blueprint.route("/<int:user_id>/role-modal")
@login_required
@require_permission(permissions=PermissionType.Admin)
def role_modal(user_id: int):
    """Get role modal content."""
    user = db.session.get(Users, user_id)
    channels = db.session.query(Channels).all()
    
    return render_template(
        "components/role_modal.html",
        user=user,
        channels=channels,
        channel_roles=ChannelRole,
        get_role_config=get_role_config
    )


@users_blueprint.route("/<int:user_id>/unban-modal")
@login_required
@require_permission(permissions=PermissionType.Admin)
def unban_modal(user_id: int):
    """Get unban modal content."""
    user = db.session.get(Users, user_id)
    
    return render_template(
        "components/unban_modal.html",
        user=user
    )


@users_blueprint.route("/external_user/<int:external_user_id>/broadcaster/<int:broadcaster_id>")
@login_required
@require_permission()
def external_user(external_user_id: int, broadcaster_id: int):
    try:
        external_user = db.session.query(
            ExternalUser).filter_by(id=external_user_id).one()

        user_weight = db.session.query(ExternalUserWeight).filter_by(
            external_user_id=external_user_id,
            broadcaster_id=broadcaster_id
        ).one_or_none()

        if user_weight:
            weights = [user_weight]
        else:
            weights = []

        submissions = db.session.query(ContentQueueSubmission).filter_by(
            user_id=external_user_id
        ).order_by(ContentQueueSubmission.submitted_at.desc()).all()

        return render_template(
            "external_user.html",
            external_user=external_user,
            broadcaster_id=broadcaster_id,
            weights=weights,
            submissions=submissions
        )
    except Exception as e:
        logger.error("Error loading external user %s: %s",
                     external_user_id, e, extra={"user_id": current_user.id})
        return "<div class='alert alert-danger'>Error loading user details</div>", 500


@users_blueprint.route("/<int:user_id>/permission/<permission_name>")
@login_required
@require_permission(permissions=PermissionType.Admin)
def grant_permission(user_id: int, permission_name: str):
    logger.info(
        "Granting '%s' to %s", permission_name, user_id
    )

    user = UserService.get_by_id(user_id)
    _ = user.add_permissions(PermissionType[permission_name])
    users = UserService.get_all()
    return render_template(
        "users.html", users=users, permission_types=PermissionType
    )


@users_blueprint.route("/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@require_permission(permissions=PermissionType.Admin)
def user_edit(user_id: int):
    user = UserService.get_by_id(user_id)
    if request.method == "GET":
        logger.info("Loaded users.html")
        broadcasters = BroadcasterService.get_all()
        return render_template(
            "user_edit.html",
            user=user,
            broadcasters=broadcasters,
            permission_types=PermissionType,
        )
    elif request.method == "POST":
        try:
            broadcaster_id = int(request.form["broadcaster_id"])
            user.broadcaster_id = broadcaster_id
            db.session.commit()
            logger.info(
                f"Changing broadcaster_id to: %s", broadcaster_id
            )
            return redirect(request.referrer)
        except:
            user.broadcaster_id = None
            db.session.commit()
            logger.info("Changing broadcaster_id to: None")
            return redirect(request.referrer)

    else:
        return "You do not have permission to modify this user", 403
