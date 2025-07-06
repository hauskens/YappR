from flask import Blueprint, render_template, jsonify, flash, redirect, request, url_for
from app.logger import logger
from flask_login import current_user, login_required # type: ignore
from datetime import datetime, timedelta, timezone
from app.models.db import ContentQueue, ExternalUserWeight, db, ExternalUser, ContentQueueSubmission
from app.retrievers import get_broadcaster_by_external_id, get_content_queue
from app.permissions import require_permission
from app.content_queue import clip_score
from flask_socketio import SocketIO
import random

socketio = SocketIO()

clip_queue_blueprint = Blueprint('clip_queue', __name__, url_prefix='/clip_queue', template_folder='templates', static_folder='static')
@clip_queue_blueprint.route("", strict_slashes=False)
def clip_queue():
    logger.info("Loading clip queue")
    messages = [
        "Hi mom :)",
        "Don't forget to thank your local server admin",
        "Wow, streamer is *that* desperate for clips?",
        "Mods asleep, post frogs",
        "Reminder to hydrate",
        "Posture check",
        "It's probably time to touch some grass",
        "If you are reading this, VI VON ZULUL",
        "You just lost the game",
        "Out of content again, are we?",
        "You are now breathing manually",
        "The cake is a lie, the cake is a lie, the cake is a...",
    ]
    if current_user.is_anonymous:
        return render_template("promo.html")
    else:
        try:
            logger.info("Loading clip queue", extra={"user_id": current_user.id})
            broadcaster = get_broadcaster_by_external_id(current_user.external_account_id) 
            if broadcaster is None:
                return render_template("promo.html")
            queue_items = get_content_queue(broadcaster.id)
            if broadcaster.last_active() is None or broadcaster.last_active() < datetime.now() - timedelta(minutes=10):
                queue_items = [item for item in queue_items if item.content.url != "https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
            logger.info("Successfully loaded clip queue", extra={"broadcaster_id": broadcaster.id, "queue_items": len(queue_items), "user_id": current_user.id})
            return render_template(
                "clip_queue_v2.html",
                queue_items=queue_items,
                broadcaster=broadcaster,
                motd=random.choice(messages),
                now=datetime.now(),
            )
        except Exception as e:
            logger.error("Error loading clip queue %s", e)
            return "You do not have access", 403


# Todo add permission check for broadcaster
@clip_queue_blueprint.route("/mark_watched/<int:item_id>", methods=["POST"])
@login_required
@require_permission()
def mark_clip_watched(item_id: int):
    """Mark a content queue item as watched"""
    try:
        queue_item = db.session.query(ContentQueue).filter_by(id=item_id).one()
        broadcaster_id = queue_item.broadcaster_id
        
        # Check if user has permission to mark this clip as watched
            
        if queue_item.watched:
            logger.info("Unmarking clip as watched", extra={"queue_item_id": queue_item.id, "user_id": current_user.id})
            queue_item.watched = False
            queue_item.watched_at = None
        else:
            logger.info("Marking clip as watched", extra={"queue_item_id": queue_item.id, "user_id": current_user.id})
            queue_item.watched = True
            queue_item.watched_at = datetime.now()
        db.session.commit()
        return jsonify({"status": "success", "watched": queue_item.watched})
    except Exception as e:
        logger.error("Error marking clip %s as watched %s", item_id, e, extra={"user_id": current_user.id})
        db.session.rollback()
        flash("Error marking clip as watched", "error")
        return redirect(request.referrer)


@clip_queue_blueprint.route("/item/<int:item_id>/skip", methods=["POST"])
@login_required
@require_permission()
def skip_clip_queue_item(item_id: int):
    """Toggle the skip status of a content queue item"""
    try:
        # Get the content queue item
        queue_item = db.session.query(ContentQueue).filter_by(id=item_id).one()
    
        if queue_item.skipped:
            logger.info("Unskipping clip", extra={"queue_item_id": queue_item.id, "user_id": current_user.id})
            queue_item.skipped = False
        else:
            logger.info("Skipping clip", extra={"queue_item_id": queue_item.id, "user_id": current_user.id})
            queue_item.skipped = True
        db.session.commit()
        socketio.emit(
            "queue_update",
            to=f"queue-{queue_item.broadcaster_id}",
        )
        return jsonify({"skipped": queue_item.skipped})
    except Exception as e:
        logger.error("Error updating skip status for item %s: %s", item_id, e, extra={"user_id": current_user.id})
        db.session.rollback()
        flash("Error updating skip status", "error")
        return redirect(request.referrer)


@clip_queue_blueprint.route("/skip_all", methods=["POST"])
@login_required
@require_permission()
def skip_all_queue_items():
    """Mark all unwatched and non-skipped queue items as skipped"""
    try:
        broadcaster = get_broadcaster_by_external_id(current_user.external_account_id)
        if broadcaster is None:
            return jsonify({"error": "Broadcaster not found"}), 404
            
        # Get all unwatched and non-skipped items in the queue
        queue_items = db.session.query(ContentQueue).filter_by(
            broadcaster_id=broadcaster.id,
            watched=False,
            skipped=False
        ).all()
        
        count = 0
        for item in queue_items:
            item.skipped = True
            count += 1
            
        db.session.commit()
        logger.info(f"Marked {count} queue items as skipped", extra={"user_id": current_user.id, "broadcaster_id": broadcaster.id})
        
        return jsonify({"status": "success", "count": count})
    except Exception as e:
        logger.error(f"Error skipping all queue items: {e}", extra={"user_id": current_user.id})
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@clip_queue_blueprint.route("/items")
@login_required
@require_permission()
def get_queue_items():
    logger.info("Loading clip queue items")
    try:
        # Check if we should show history (watched clips)
        show_history = request.args.get('show_history', 'false').lower() == 'true'
        prefer_shorter = request.args.get('prefer_shorter', 'false').lower() == 'true'
        
        # Search parameter
        search_query = request.args.get('search', '').strip()
        
        # Support pagination - default to 20 items per page
        page = max(int(request.args.get('page', 1)), 1)  # Ensure page is at least 1
        limit = int(request.args.get('limit', 20))
        offset = (page - 1) * limit
        
        broadcaster = get_broadcaster_by_external_id(current_user.external_account_id) 
        queue_enabled = False
        for channel in broadcaster.channels:
            if channel.platform.name.lower() == "twitch" and channel.settings.content_queue_enabled:
                queue_enabled = True
                break
        if broadcaster is not None and queue_enabled:
            # Include watched and skipped clips if show_history is True
            queue_items = get_content_queue(broadcaster.id, include_watched=show_history, include_skipped=show_history)
            
            # Filter out rickroll if not active and not admin/mod
            if (broadcaster.last_active() is None or broadcaster.last_active() < datetime.now() - timedelta(minutes=10)) and not current_user.has_permission(["mod", "admin"]):
                queue_items = [item for item in queue_items if item.content.url != "https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
                
            # If showing history tab, filter to only include watched or skipped items
            if show_history:
                queue_items = [item for item in queue_items if item.watched or item.skipped]
            
            # Apply search filter if provided
            if search_query:
                queue_items = [
                    item for item in queue_items if 
                    search_query.lower() in item.content.title.lower() or
                    search_query.lower() in item.content.channel_name.lower() or
                    any(submission.user_comment and search_query.lower() in submission.user_comment.lower() for submission in item.submissions) or
                    any(search_query.lower() in submission.user.username.lower() for submission in item.submissions)
                ]
            
            # Sort items - for history tab, we might want to sort differently
            now = datetime.now(timezone.utc)
            if show_history:
                # For history, sort by watched_at time (most recent first)
                queue_items = sorted(queue_items, key=lambda item: item.watched_at if item.watched_at else datetime.min, reverse=True)
            else:
                # For upcoming queue, sort by score
                queue_items.sort(key=lambda item: clip_score(item, now=now, prefer_shorter=prefer_shorter), reverse=True)
                
            # Store total count before pagination
            total_items = len(queue_items)
            
            # Apply pagination
            paginated_items = queue_items[offset:offset + limit]
            
            # Check if there are more items to load
            has_more = total_items > offset + limit
            next_page = page + 1 if has_more else None
            
            if len(paginated_items) == 0 and page == 1:
                return "No clips found" if show_history else "No more clips :("
            elif len(paginated_items) == 0:
                return "" # Return empty for additional pages with no content
                
            logger.info("Successfully loaded clip queue items", extra={
                "broadcaster_id": broadcaster.id, 
                "queue_items": len(paginated_items),
                "total_items": total_items,
                "page": page,
                "has_more": has_more,
                "user_id": current_user.id,
                "show_history": show_history,
                "prefer_shorter": prefer_shorter
            })
            
            return render_template(
                "clip_queue_items.html",
                queue_items=paginated_items,
                broadcaster=broadcaster,
                now=datetime.now(),
                show_history=show_history,
                prefer_shorter=prefer_shorter,
                page=page,
                has_more=has_more,
                next_page=next_page,
                search_query=search_query
            )
        elif broadcaster is not None and not queue_enabled:
            return "You have disabled the queue, visit <a href='/broadcaster/edit/" + str(broadcaster.id) + "'>broadcaster settings</a> to enable it"
        else:
            return "You do not have access, no broadcaster_id found on you", 403
    except Exception as e:
        logger.error("Error loading clip queue items %s", e, extra={"user_id": current_user.id})
        return "Error loading clip queue items", 500


@clip_queue_blueprint.route("/details/<int:item_id>")
@login_required
@require_permission()
def get_clip_details(item_id: int):
    """Get details for a specific clip to display in the player area"""
    try:
        queue_item = db.session.query(ContentQueue).filter_by(id=item_id).one()
        return render_template(
            "clip_details.html",
            item=queue_item,
            now=datetime.now(),
        )
    except Exception as e:
        logger.error("Error loading clip details %s", e, extra={"item_id": item_id, "user_id": current_user.id})
        return "Error loading clip details", 500


@clip_queue_blueprint.route("/player/<int:item_id>")
@login_required
@require_permission()
def get_clip_player(item_id: int):
    """Get the player HTML for a specific clip"""
    try:
        queue_item = db.session.query(ContentQueue).filter_by(id=item_id).one()
        return render_template(
            "clip_player.html",
            item=queue_item,
        )
    except Exception as e:
        logger.error("Error loading clip player %s", e, extra={"item_id": item_id, "user_id": current_user.id})
        return "Error loading clip player", 500

@clip_queue_blueprint.route("/<int:broadcaster_id>/external_user/<int:external_user_id>/penalty", methods=["POST"])
@login_required
# @require_permission(require_broadcaster=True, broadcaster_id_param="broadcaster_id", require_moderator=True)
def penalty_external_user(broadcaster_id: int, external_user_id: int):
    standard_penalty = 0.2
    standard_ban_duration = 7
    force_ban = request.args.get('ban', 'false').lower() == 'true'
    
    try:
        external_user_weight = db.session.query(ExternalUserWeight).filter_by(external_user_id=external_user_id, broadcaster_id=broadcaster_id).one_or_none()
        if external_user_weight is None:
            external_user_weight = ExternalUserWeight(
                external_user_id=external_user_id,
                broadcaster_id=broadcaster_id,
                weight=1,
                banned=False,
                banned_at=None,
                unban_at=None,
            )
            db.session.add(external_user_weight)
        
        if force_ban:
            logger.info(f"Force banning user {external_user_id}", extra={"user_id": current_user.id})
            external_user_weight.weight = 0
            external_user_weight.banned = True
            external_user_weight.banned_at = datetime.now()
            external_user_weight.unban_at = datetime.now() + timedelta(days=standard_ban_duration)
        else:
            # Apply standard penalty
            external_user_weight.weight = round(external_user_weight.weight - standard_penalty, 2)
            if external_user_weight.weight <= 0:
                external_user_weight.weight = 0
                external_user_weight.banned = True
                external_user_weight.banned_at = datetime.now()
                external_user_weight.unban_at = datetime.now() + timedelta(days=standard_ban_duration)
        
        db.session.commit()
        # Redirect to the external_user route in users_blueprint
        return redirect(url_for('users.external_user', external_user_id=external_user_id, broadcaster_id=broadcaster_id))
    except Exception as e:
        logger.error("Error updating penalty status for external user %s: %s", external_user_id, e, extra={"user_id": current_user.id})
        db.session.rollback()
        flash("Error updating penalty status", "error")
        return redirect(url_for('users.external_user', external_user_id=external_user_id, broadcaster_id=broadcaster_id))

@clip_queue_blueprint.route("/<int:broadcaster_id>/external_user/<int:external_user_id>/reset_penalties", methods=["POST"])
@login_required
# @require_permission(require_broadcaster=True, broadcaster_id_param="broadcaster_id", require_moderator=True)
def reset_external_user_penalties(broadcaster_id: int, external_user_id: int):
    try:
        # Get the external user
        external_user = db.session.query(ExternalUser).filter_by(id=external_user_id).one()
        
        # Get or create user weight
        external_user_weight = db.session.query(ExternalUserWeight).filter_by(
            external_user_id=external_user_id, 
            broadcaster_id=broadcaster_id
        ).one_or_none()
        
        if external_user_weight is None:
            # If no weight exists, create a default one with standard values
            external_user_weight = ExternalUserWeight(
                external_user_id=external_user_id,
                broadcaster_id=broadcaster_id,
                weight=1.0,
                banned=False,
                banned_at=None,
                unban_at=None
            )
            db.session.add(external_user_weight)
        else:
            # Reset weight to 1.0 and unban
            external_user_weight.weight = 1.0
            external_user_weight.banned = False
            external_user_weight.unban_at = None
        
        db.session.commit()
        
        # Get submissions for template rendering
        submissions = db.session.query(ContentQueueSubmission).filter_by(
            user_id=external_user_id
        ).order_by(ContentQueueSubmission.submitted_at.desc()).all()
        
        # Redirect to the external_user route in users_blueprint
        return redirect(url_for('users.external_user', external_user_id=external_user_id, broadcaster_id=broadcaster_id))
    except Exception as e:
        logger.error("Error resetting penalties for external user %s: %s", external_user_id, e, extra={"user_id": current_user.id})
        db.session.rollback()
        flash("An error occurred while resetting penalties.", "danger")
        
        # In case of error, try to get data for the template
        try:
            external_user = db.session.query(ExternalUser).filter_by(id=external_user_id).one()
            user_weight = db.session.query(ExternalUserWeight).filter_by(
                external_user_id=external_user_id,
                broadcaster_id=broadcaster_id
            ).one_or_none()
            weights = [user_weight] if user_weight else []
            submissions = db.session.query(ContentQueueSubmission).filter_by(
                user_id=external_user_id
            ).order_by(ContentQueueSubmission.submitted_at.desc()).all()
            
            return redirect(url_for('users.external_user', external_user_id=external_user_id, broadcaster_id=broadcaster_id))
        except Exception:
            return "<div class='alert alert-danger'>Error loading user details</div>", 500