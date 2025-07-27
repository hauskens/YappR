from flask import Blueprint, render_template, request, redirect
from flask_login import current_user, login_required  # type: ignore
from app.permissions import require_permission
from app.models import db
from app.models.user import ExternalUser, ExternalUserWeight
from app.models.content_queue import ContentQueueSubmission
from app.models.enums import PermissionType
from app.logger import logger
from app.services.broadcaster import BroadcasterService
from app.retrievers import get_user_by_id, get_users

users_blueprint = Blueprint('users', __name__, url_prefix='/users',
                            template_folder='templates', static_folder='static')


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

    user = get_user_by_id(user_id)
    _ = user.add_permissions(PermissionType[permission_name])
    users = get_users()
    return render_template(
        "users.html", users=users, permission_types=PermissionType
    )


@users_blueprint.route("/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@require_permission(permissions=PermissionType.Admin)
def user_edit(user_id: int):
    user = get_user_by_id(user_id)
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
