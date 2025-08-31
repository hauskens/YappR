from flask import Blueprint, render_template, jsonify, flash, redirect, request, url_for
from app.logger import logger
from flask_login import current_user, login_required  # type: ignore
from datetime import datetime, timedelta, timezone
from app.models import db
from app.models import PermissionType, ContentQueueSettings, ContentQueueSubmission, ContentQueue, Users, UserWeight, UserChannelRole
from app.models.enums import ChannelRole
from app.platforms.handler import PlatformRegistry
from app.retrievers import get_content_queue
from app.services import BroadcasterService, UserService, ModerationService
from app.services.content_queue import WeightSettingsService
from app.permissions import require_permission, check_permission, check_banned
import random
from sqlalchemy import select


def is_user_trusted(user_id: int, broadcaster_id: int) -> bool:
    """Check if a user has VIP, MOD, or Owner role for a specific broadcaster."""
    try:
        # Get user object
        user = db.session.query(Users).filter_by(id=user_id).first()
        if not user:
            return False
            
        # Get broadcaster's channels
        broadcaster = BroadcasterService.get_by_id(broadcaster_id)
        if not broadcaster or not broadcaster.channels:
            return False
        
        # Check if user has VIP, MOD, or Owner role in any of the broadcaster's channels
        trusted_roles = [ChannelRole.VIP, ChannelRole.Mod, ChannelRole.Owner]
        for channel in broadcaster.channels:
            user_role = UserService.get_channel_role(user, channel.id)
            if user_role and user_role in trusted_roles:
                return True
        
        return False
    except Exception as e:
        logger.error(f"Error checking if user {user_id} is trusted for broadcaster {broadcaster_id}: {e}")
        return False


clip_queue_blueprint = Blueprint(
    'clip_queue', __name__, url_prefix='/clip_queue', template_folder='templates', static_folder='static')


@clip_queue_blueprint.route("", strict_slashes=False)
@check_banned()
def clip_queue():
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
        logger.info("Anonymous user accessing clip queue, sending to promo")
        return render_template("promo.html")
    else:
        try:
            logger.info("Loading clip queue", extra={
                        "user_id": current_user.id})
            broadcaster = BroadcasterService.get_by_external_id(
                current_user.external_account_id)
            if broadcaster is None:
                logger.info("User is not a broadcaster, sending to promo")
                return render_template("promo.html")
            queue_items = get_content_queue(broadcaster.id)
            if BroadcasterService.get_last_active(broadcaster.id) is None or BroadcasterService.get_last_active(broadcaster.id) < datetime.now() - timedelta(minutes=10):
                queue_items = [item for item in queue_items if item.content.url !=
                               "https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
            logger.info("Successfully loaded clip queue", extra={
                        "broadcaster_id": broadcaster.id, "queue_items": len(queue_items), "user_id": current_user.id})
            return render_template(
                "clip_queue_v2.html",
                queue_items=queue_items,
                broadcaster=broadcaster,
                motd=random.choice(messages),
                now=datetime.now(),
            )
        except Exception as e:
            logger.error("Error loading clip queue %s", e)
            return "You do not have access", 401


# Todo add permission check for broadcaster
@clip_queue_blueprint.route("/mark_watched/<int:item_id>", methods=["POST"])
@login_required
@require_permission(check_broadcaster=True, permissions=PermissionType.Moderator)
def mark_clip_watched(item_id: int):
    """Mark a content queue item as watched"""
    try:
        queue_item = db.session.query(ContentQueue).filter_by(id=item_id).one()
        broadcaster_id = queue_item.broadcaster_id

        # Check if user has permission to mark this clip as watched
        broadcaster = BroadcasterService.get_by_external_id(
            current_user.external_account_id)
        
        # Admins and global moderators can mark any clip as watched
        if UserService.has_permission(current_user, [PermissionType.Admin, PermissionType.Moderator]):
            pass  # Allow access
        # Otherwise, user must be the broadcaster for this specific queue item
        elif broadcaster is None or broadcaster_id != broadcaster.id:
            return jsonify({"error": "You do not have permission to mark this clip as watched"}), 401

        if queue_item.watched:
            logger.info("Unmarking clip as watched", extra={
                        "queue_item_id": queue_item.id, "user_id": current_user.id})
            queue_item.watched = False
            queue_item.watched_at = None
            queue_item.score = 0.0
        else:
            logger.info("Marking clip as watched", extra={
                        "queue_item_id": queue_item.id, "user_id": current_user.id})
            queue_item.watched = True
            queue_item.watched_at = datetime.now()
            rating = float(request.form.get('rating', 0.0))
            rating = max(-1.0, min(1.0, rating))
            queue_item.score = rating
        db.session.commit()
        return jsonify({"status": "success", "watched": queue_item.watched})
    except Exception as e:
        logger.error("Error marking clip %s as watched %s",
                     item_id, e, extra={"user_id": current_user.id})
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
        broadcaster_id = queue_item.broadcaster_id

        # Check if user has permission to skip this clip
        broadcaster = BroadcasterService.get_by_external_id(
            current_user.external_account_id)
        
        # Admins and global moderators can skip any clip
        if UserService.has_permission(current_user, [PermissionType.Admin, PermissionType.Moderator]):
            pass  # Allow access
        # Channel moderators for this broadcaster can skip clips
        elif UserService.is_moderator(current_user, broadcaster_id):
            pass  # Allow access
        # Otherwise, user must be the broadcaster for this specific queue item
        elif broadcaster is None or broadcaster_id != broadcaster.id:
            return jsonify({"error": "You do not have permission to skip this clip"}), 401
        if queue_item.skipped:
            logger.info("Unskipping clip", extra={
                        "queue_item_id": queue_item.id, "user_id": current_user.id})
            queue_item.skipped = False
        else:
            logger.info("Skipping clip", extra={
                        "queue_item_id": queue_item.id, "user_id": current_user.id})
            queue_item.skipped = True
        db.session.commit()
        return jsonify({"skipped": queue_item.skipped})
    except Exception as e:
        logger.error("Error updating skip status for item %s: %s",
                     item_id, e, extra={"user_id": current_user.id})
        db.session.rollback()
        flash("Error updating skip status", "error")
        return redirect(request.referrer)


@clip_queue_blueprint.route("/skip_all", methods=["POST"])
@login_required
@require_permission()
def skip_all_queue_items():
    """Mark all unwatched and non-skipped queue items as skipped"""
    try:
        broadcaster = BroadcasterService.get_by_external_id(
            current_user.external_account_id)
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
        logger.info(f"Marked {count} queue items as skipped", extra={
                    "user_id": current_user.id, "broadcaster_id": broadcaster.id})

        return jsonify({"status": "success", "count": count})
    except Exception as e:
        logger.error(f"Error skipping all queue items: {e}", extra={
                     "user_id": current_user.id})
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@clip_queue_blueprint.route("/items")
@login_required
@require_permission()
def get_queue_items():
    logger.debug("Loading clip queue items")
    try:
        # Check if we should show history (watched clips)
        show_history = request.args.get(
            'show_history', 'false').lower() == 'true'

        # Get broadcaster and content queue settings
        broadcaster = BroadcasterService.get_by_external_id(
            current_user.external_account_id)

        # Get prefer_shorter_content setting from database
        weight_settings = WeightSettingsService.get_by_broadcaster(broadcaster.id)


        # Search parameter
        search_query = request.args.get('search', '').strip()

        # Support pagination - default to 20 items per page
        # Ensure page is at least 1
        page = max(int(request.args.get('page', 1)), 1)
        limit = int(request.args.get('limit', 20))
        offset = (page - 1) * limit

        broadcaster = BroadcasterService.get_by_external_id(
            current_user.external_account_id)
        queue_enabled = False
        for channel in broadcaster.channels:
            if str(channel.platform_name).lower() == "twitch" and channel.settings.content_queue_enabled:
                queue_enabled = True
                break
        if broadcaster is not None and queue_enabled:
            # Include watched and skipped clips if show_history is True
            queue_items = get_content_queue(
                broadcaster.id, include_watched=show_history, include_skipped=show_history)

            # Filter out rickroll if not active and not admin/mod
            if (BroadcasterService.get_last_active(broadcaster.id) is None or BroadcasterService.get_last_active(broadcaster.id) < datetime.now() - timedelta(minutes=10)) and not UserService.has_permission(current_user, [PermissionType.Moderator, PermissionType.Admin]):
                queue_items = [item for item in queue_items if item.content.url !=
                               "https://www.youtube.com/watch?v=dQw4w9WgXcQ"]

            # If showing history tab, filter to only include watched or skipped items
            if show_history:
                queue_items = [
                    item for item in queue_items if item.watched or item.skipped]

            # Apply search filter if provided
            if search_query:
                queue_items = [
                    item for item in queue_items if
                    search_query.lower() in item.content.title.lower() or
                    search_query.lower() in item.content.channel_name.lower() or
                    any(submission.user_comment and search_query.lower() in submission.user_comment.lower() for submission in item.submissions) or
                    any(search_query.lower() in submission.user.name.lower()
                        for submission in item.submissions)
                ]

            # Sort items - for history tab, we might want to sort differently
            now = datetime.now(timezone.utc)
            if show_history:
                # For history, sort by watched_at time (most recent first)
                queue_items = sorted(
                    queue_items, key=lambda item: item.watched_at if item.watched_at else datetime.min, reverse=True)
            else:
                logger.debug("Sorting queue items by score using the new WeightService calculation")
                # For upcoming queue, sort by score using the new WeightService calculation
                for item in queue_items:
                    try:
                        if not item.submissions:
                            # If no submissions, set a default age
                            age_minutes = 0
                        else:
                            earliest_submission = min(item.submissions, key=lambda s: s.submitted_at)
                            # Ensure both datetimes have timezone information
                            submission_time = earliest_submission.submitted_at
                            if submission_time.tzinfo is None:
                                # Convert naive datetime to aware datetime with UTC timezone
                                submission_time = submission_time.replace(tzinfo=timezone.utc)
                            age_minutes = int((now - submission_time).total_seconds() / 60)
                    except Exception as e:
                        logger.error(f"Error calculating age_minutes: {e}")
                        # Use a default value if calculation fails
                        age_minutes = 0
                    # Check if any submitter is trusted (VIP/MOD/Owner)
                    is_trusted = False
                    if item.submissions:
                        # Check if any submitter has VIP/MOD/Owner role for this broadcaster
                        is_trusted = any(
                            is_user_trusted(submission.user_id, broadcaster.id) 
                            for submission in item.submissions
                        )
                    
                    # Calculate score using weight settings
                    final_score, _ = WeightSettingsService.calculate_score(
                        weight_settings=weight_settings,
                        base_popularity=len(item.submissions),
                        age_minutes=age_minutes,
                        duration_seconds=item.content.duration or 0,  # Handle None values
                        is_trusted=is_trusted
                    )
                    item.score = final_score
                queue_items.sort(key=lambda item: item.score, reverse=True)

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
                return ""  # Return empty for additional pages with no content

            logger.debug("Successfully loaded clip queue items", extra={
                "broadcaster_id": broadcaster.id,
                "queue_items": len(paginated_items),
                "total_items": total_items,
                "page": page,
                "has_more": has_more,
                "user_id": current_user.id,
                "show_history": show_history,
            })

            try:
                # Make all queue item datetime fields timezone-aware before passing to template
                for item in paginated_items:
                    if hasattr(item, 'watched_at') and item.watched_at and item.watched_at.tzinfo is None:
                        item.watched_at = item.watched_at.replace(tzinfo=timezone.utc)
                    
                    # Ensure all submission datetimes are timezone-aware
                    if hasattr(item, 'submissions'):
                        for submission in item.submissions:
                            if submission.submitted_at and submission.submitted_at.tzinfo is None:
                                submission.submitted_at = submission.submitted_at.replace(tzinfo=timezone.utc)
                
                return render_template(
                    "clip_queue_items.html",
                    queue_items=paginated_items,
                    broadcaster=broadcaster,
                    now=datetime.now(timezone.utc),
                    show_history=show_history,
                    page=page,
                    has_more=has_more,
                    next_page=next_page,
                    search_query=search_query,
                    weight_settings_service=WeightSettingsService,
                    timezone=timezone,
                    is_user_trusted=is_user_trusted
                )
            except Exception as e:
                logger.error(f"Error rendering template: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                return f"Error rendering template: {str(e)}", 500
        elif broadcaster is not None and not queue_enabled:
            return "You have disabled the queue, visit <a href='/broadcaster/edit/" + str(broadcaster.id) + "'>broadcaster settings</a> to enable it"
        else:
            return "You do not have access, no broadcaster_id found on you", 401
    except Exception as e:
        logger.error("Error loading clip queue items %s",
                     e, extra={"user_id": current_user.id})
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
        logger.error("Error loading clip details %s", e, extra={
                     "item_id": item_id, "user_id": current_user.id})
        return "Error loading clip details", 500


@clip_queue_blueprint.route("/player/<int:item_id>")
@login_required
@require_permission()
def get_clip_player(item_id: int):
    """Get the player HTML for a specific clip"""
    try:
        queue_item = db.session.query(ContentQueue).filter_by(id=item_id).one()
        url = queue_item.content.url if queue_item.content.url else queue_item.content.stripped_url
        handler = None

        if url:
            try:
                handler = PlatformRegistry.get_handler_by_url(url)
            except Exception as handler_ex:
                logger.warning(
                    f"Failed to get platform handler for URL {url}: {str(handler_ex)}")

        return render_template(
            "clip_player.html",
            item=queue_item,
            handler=handler,
        )
    except Exception as e:
        logger.error("Error loading clip player %s", e, extra={
                     "item_id": item_id, "user_id": current_user.id})
        return "Error loading clip player", 500


@clip_queue_blueprint.route("/<int:broadcaster_id>/external_user/<int:external_user_id>/penalty", methods=["POST"])
@login_required
@require_permission(check_broadcaster=True, check_moderator=True)
def penalty_external_user(broadcaster_id: int, external_user_id: int):
    standard_penalty = 0.2
    standard_ban_duration = 7
    force_ban = request.args.get('ban', 'false').lower() == 'true'

    try:
        user_weight = db.session.query(UserWeight).filter_by(
            user_id=external_user_id, broadcaster_id=broadcaster_id).one_or_none()
        if user_weight is None:
            user_weight = UserWeight(
                user_id=external_user_id,
                broadcaster_id=broadcaster_id,
                weight=1,
                banned=False,
                banned_at=None,
                unban_at=None,
            )
            db.session.add(user_weight)

        if force_ban:
            logger.info(f"Force banning user {external_user_id}", extra={
                        "user_id": current_user.id})
            user_weight.weight = 0
            user_weight.banned = True
            user_weight.banned_at = datetime.now()
            user_weight.unban_at = datetime.now(
            ) + timedelta(days=standard_ban_duration)
        else:
            # Apply standard penalty
            user_weight.weight = round(
                user_weight.weight - standard_penalty, 2)
            if user_weight.weight <= 0:
                user_weight.weight = 0
                user_weight.banned = True
                user_weight.banned_at = datetime.now()
                user_weight.unban_at = datetime.now(
                ) + timedelta(days=standard_ban_duration)

        db.session.commit()
        # Redirect to the external_user route in users_blueprint
        return redirect(url_for('users.external_user', external_user_id=external_user_id, broadcaster_id=broadcaster_id))
    except Exception as e:
        logger.error("Error updating penalty status for external user %s: %s",
                     external_user_id, e, extra={"user_id": current_user.id})
        db.session.rollback()
        flash("Error updating penalty status", "error")
        return redirect(url_for('users.external_user', external_user_id=external_user_id, broadcaster_id=broadcaster_id))


@clip_queue_blueprint.route("/<int:broadcaster_id>/external_user/<int:external_user_id>/reset_penalties", methods=["POST"])
@login_required
@require_permission(check_broadcaster=True, check_moderator=True)
def reset_external_user_penalties(broadcaster_id: int, external_user_id: int):
    logger.info("Resetting external user penalties", extra={
                "broadcaster_id": broadcaster_id, "external_user_id": external_user_id})
    try:
        # Get the user
        user = db.session.query(
            Users).filter_by(id=external_user_id).one()

        # Get or create user weight
        user_weight = db.session.query(UserWeight).filter_by(
            user_id=external_user_id,
            broadcaster_id=broadcaster_id
        ).one_or_none()

        if user_weight is None:
            # If no weight exists, create a default one with standard values
            user_weight = UserWeight(
                user_id=external_user_id,
                broadcaster_id=broadcaster_id,
                weight=1.0,
                banned=False,
                banned_at=None,
                unban_at=None
            )
            db.session.add(user_weight)
        else:
            # Reset weight to 1.0 and unban
            user_weight.weight = 1.0
            user_weight.banned = False
            user_weight.unban_at = None

        db.session.commit()

        # Get submissions for template rendering
        submissions = db.session.query(ContentQueueSubmission).filter_by(
            user_id=external_user_id
        ).order_by(ContentQueueSubmission.submitted_at.desc()).all()

        # Redirect to the external_user route in users_blueprint
        return redirect(url_for('users.external_user', external_user_id=external_user_id, broadcaster_id=broadcaster_id))
    except Exception as e:
        logger.error("Error resetting penalties for external user %s: %s",
                     external_user_id, e, extra={"user_id": current_user.id})
        db.session.rollback()
        flash("An error occurred while resetting penalties.", "danger")

        # In case of error, try to get data for the template
        try:
            user = db.session.query(
                Users).filter_by(id=external_user_id).one()
            user_weight = db.session.query(UserWeight).filter_by(
                user_id=external_user_id,
                broadcaster_id=broadcaster_id
            ).one_or_none()
            weights = [user_weight] if user_weight else []
            submissions = db.session.query(ContentQueueSubmission).filter_by(
                user_id=external_user_id
            ).order_by(ContentQueueSubmission.submitted_at.desc()).all()

            return redirect(url_for('users.external_user', external_user_id=external_user_id, broadcaster_id=broadcaster_id))
        except Exception:
            return "<div class='alert alert-danger'>Error loading user details</div>", 500


@clip_queue_blueprint.route("/settings", methods=["GET", "POST"])
@login_required
@require_permission()
def settings():
    """Get allowed platforms for the broadcaster's queue"""
    try:
        broadcaster = UserService.get_broadcaster(current_user)
        if not broadcaster:
            logger.error("Broadcaster not found")
            return jsonify({"status": "error", "message": "Broadcaster not found"}), 404

        if request.method == "POST":
            # Get selected platforms from form
            platforms = request.form.getlist("platforms")
            # Get prefer_shorter_content preference
            prefer_shorter = "prefer_shorter_content" in request.form

            # Check if this is a weight settings update
            weight_settings_fields = [
                'prefer_shorter', 'keep_fresh', 'ignore_popularity', 'boost_variety', 'viewer_priority',
                'prefer_shorter_intensity', 'keep_fresh_intensity', 'ignore_popularity_intensity',
                'boost_variety_intensity', 'viewer_priority_intensity', 'short_clip_threshold_seconds',
                'freshness_window_minutes'
            ]
            
            has_weight_settings = any(field in request.form for field in weight_settings_fields)

            logger.info(f"Updating queue settings", extra={
                "broadcaster_id": broadcaster.id,
                "platforms": platforms,
                "prefer_shorter_content": prefer_shorter,
                "has_weight_settings": has_weight_settings
            })

            # Get or create content queue settings
            queue_settings = db.session.execute(
                select(ContentQueueSettings).filter(
                    ContentQueueSettings.broadcaster_id == broadcaster.id
                )
            ).scalars().one_or_none()

            if not queue_settings:
                # Create new settings if they don't exist
                queue_settings = ContentQueueSettings(
                    broadcaster_id=broadcaster.id)
                db.session.add(queue_settings)

            # Update allowed platforms and prefer_shorter_content preference
            queue_settings.set_allowed_platforms(platforms)
            queue_settings.prefer_shorter_content = prefer_shorter
            
            # Handle weight settings if present
            if has_weight_settings:
                from app.models.content_queue_settings import WeightSettings
                
                # Get current weight settings or create defaults
                current_weight_settings = WeightSettingsService.get_by_broadcaster(broadcaster.id)
                
                # Build weight settings dict from form data
                weight_data = {}
                
                # Boolean fields
                for field in ['prefer_shorter', 'keep_fresh', 'ignore_popularity', 'boost_variety', 'viewer_priority']:
                    weight_data[field] = field in request.form
                
                # Float fields (intensity settings)
                for field in ['prefer_shorter_intensity', 'keep_fresh_intensity', 'ignore_popularity_intensity', 
                             'boost_variety_intensity', 'viewer_priority_intensity']:
                    if field in request.form:
                        try:
                            weight_data[field] = float(request.form[field])
                        except (ValueError, TypeError):
                            weight_data[field] = getattr(current_weight_settings, field)
                
                # Integer fields (advanced settings)
                for field in ['short_clip_threshold_seconds', 'freshness_window_minutes']:
                    if field in request.form:
                        try:
                            weight_data[field] = int(request.form[field])
                        except (ValueError, TypeError):
                            weight_data[field] = getattr(current_weight_settings, field)
                
                # Create new WeightSettings object and update
                try:
                    updated_weight_settings = WeightSettings(**weight_data)
                    WeightSettingsService.update_weight_settings(broadcaster.id, updated_weight_settings)
                except Exception as e:
                    logger.error(f"Error updating weight settings: {e}")
                    # Continue with platform settings update even if weight settings fail
            
            db.session.commit()

            return jsonify({
                "status": "success",
                "message": "Settings updated successfully"
            })
        elif request.method == "GET":
            # Get content queue settings
            queue_settings = db.session.execute(
                select(ContentQueueSettings).filter(
                    ContentQueueSettings.broadcaster_id == broadcaster.id
                )
            ).scalars().one_or_none()
            if not queue_settings:
                queue_settings = ContentQueueSettings(
                    broadcaster_id=broadcaster.id,
                )
                db.session.add(queue_settings)
            db.session.commit()

            platforms = queue_settings.get_allowed_platforms
            prefer_shorter = queue_settings.prefer_shorter_content
            
            # Get weight settings
            weight_settings = WeightSettingsService.get_by_broadcaster(broadcaster.id)

            response_data = {
                "status": "success",
                "platforms": platforms,
                "prefer_shorter_content": prefer_shorter
            }
            
            # Include weight settings in response
            response_data.update(weight_settings.model_dump())

            return jsonify(response_data)
    except Exception as e:
        logger.error(f"Error updating platform settings: {e}")
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


@clip_queue_blueprint.route("/add", methods=["GET", "POST"])
@login_required
@require_permission()
def add_content():
    """Add new content to the queue"""
    logger.info("Loaded add_content.html")
    try:
        if UserService.is_moderator(current_user) or UserService.is_admin(current_user):
            broadcasters = BroadcasterService.get_all(show_hidden=True)
        else:
            all_broadcasters = BroadcasterService.get_all(show_hidden=False)
            banned_channel_ids = ModerationService.get_banned_channel_ids(current_user)
            banned_broadcaster_ids = [BroadcasterService.get_by_internal_channel_id(channel_id).id for channel_id in banned_channel_ids]

            broadcasters = [broadcaster for broadcaster in all_broadcasters if broadcaster.id not in banned_broadcaster_ids]
            if UserService.is_broadcaster(current_user):
                broadcasters.append(UserService.get_broadcaster(current_user))

        user = UserService.get_by_external_id(current_user.external_account_id)
        
        if request.method == "GET":
            return render_template("add_content.html", broadcasters=broadcasters)

        elif request.method == "POST":
            url = request.form.get("url", "").strip()
            selected_broadcaster_id = int(request.form.get("broadcaster_id"))

            if selected_broadcaster_id not in [broadcaster.id for broadcaster in broadcasters]:
                return jsonify({"status": "error", "message": "Invalid broadcaster selected"}), 400

            if not url:
                return jsonify({"status": "error", "message": "URL is required"}), 400

            # Add the content to the queue using the shared function
            import asyncio
            from bot.shared import add_to_content_queue
            from app.models.content_queue import ContentQueueSubmissionSource
            from app.twitch_api import get_twitch_client

            broadcaster = BroadcasterService.get_by_id(selected_broadcaster_id)
            # Use asyncio.run to handle the async function
            async def add_content_async():
                # Initialize Twitch client for Twitch URLs
                twitch_client = None
                try:
                    if 'twitch.tv' in url.lower():
                        twitch_client = await get_twitch_client()
                        await twitch_client.authenticate_app([])
                except Exception as e:
                    logger.warning(f"Failed to initialize Twitch client: {e}")
                    twitch_client = None

                return await add_to_content_queue(
                    url=url,
                    broadcaster_id=selected_broadcaster_id,
                    username=user.name,
                    external_user_id=user.external_account_id,
                    submission_source_type=ContentQueueSubmissionSource.Web,
                    submission_source_id=0,
                    submission_weight=1.0,
                    twitch_client=twitch_client
                )

            queue_item_id = asyncio.run(add_content_async())

            if queue_item_id:
                return f"<div class='alert alert-success'><i class='bi bi-check-circle me-2'></i>Content successfully submitted to the {broadcaster.name}'s queue!</div>"
            else:
                return "<div class='alert alert-danger'><i class='bi bi-exclamation-triangle me-2'></i>Failed to add content or content not supported.</div>"

    except Exception as e:
        logger.error(f"Error adding content: {e}")
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


@clip_queue_blueprint.route("/search", methods=["POST"])
@login_required
@require_permission()
def search_content():
    """Search for existing content in the queue by URL or text"""
    logger.info("User searching for clip")
    try:
        query = request.form.get("url", "").strip()
        broadcaster_id = request.form.get("broadcaster_id")

        if not query:
            return jsonify({"status": "error", "message": "Search query is required"}), 400

        # First, try to detect if this is a URL
        is_url = False
        try:
            platform_handler = PlatformRegistry.get_handler_by_url(query)
            deduplicated_url = platform_handler.deduplicate_url()
            is_url = True
        except ValueError:
            # Not a valid URL, will do text search instead
            is_url = False

        if is_url:
            # URL search - existing logic
            from app.models.content_queue import Content
            existing_content = db.session.execute(
                select(Content).filter(
                    (Content.url == query) | (
                        Content.stripped_url == deduplicated_url)
                )
            ).scalars().one_or_none()

            if existing_content:
                # If no broadcaster specified, search across all allowed broadcasters
                if not broadcaster_id:
                    if check_permission(current_user, permissions=[PermissionType.Admin, PermissionType.Moderator]):
                        broadcasters = BroadcasterService.get_all(
                            show_hidden=True)
                    else:
                        if UserService.is_broadcaster(current_user):
                            broadcasters = [
                                UserService.get_broadcaster(current_user)]
                        broadcasters += BroadcasterService.get_all(
                            show_hidden=False)
                    # Get all queue items for this content across all broadcasters
                    all_queue_items = db.session.execute(
                        select(ContentQueue).filter(
                            ContentQueue.content_id == existing_content.id,
                            ContentQueue.broadcaster_id.in_(
                                [broadcaster.id for broadcaster in broadcasters])
                        )
                    ).scalars().all()

                    if all_queue_items:
                        return render_template("management_items.html",
                                               queue_items=all_queue_items,
                                               total_items=len(
                                                   all_queue_items),
                                               total_pages=1,
                                               page=1,
                                               search_query="")
                else:
                    # Search in specific broadcaster's queue
                    broadcaster_id = int(broadcaster_id)
                    existing_queue_item = db.session.execute(
                        select(ContentQueue).filter(
                            ContentQueue.content_id == existing_content.id,
                            ContentQueue.broadcaster_id == broadcaster_id
                        )
                    ).scalars().one_or_none()

                    if existing_queue_item:
                        return render_template("management_items.html",
                                               queue_items=[
                                                   existing_queue_item],
                                               total_items=1,
                                               total_pages=1,
                                               page=1,
                                               search_query="")

            # No content found for URL
            return "<div class='alert alert-info'>No existing content found for this URL.</div>"
        else:
            # Text search - sanitize input first
            import re
            sanitized_query = re.sub(r'[^a-zA-Z0-9\s_-]', '', query)
            sanitized_query = sanitized_query.strip()

            if not sanitized_query:
                return "<div class='alert alert-warning'>Search query contains no valid characters. Only letters, numbers, spaces, hyphens, and underscores are allowed.</div>"

            # Call the text search function directly
            return text_search_content_internal(sanitized_query, broadcaster_id)

    except Exception as e:
        logger.error(f"Error searching content: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@clip_queue_blueprint.route("/text-search", methods=["POST"])
@login_required
@require_permission()
def text_search_content():
    """Search for content by text in title, channel name, or user comments"""
    try:
        query = request.form.get("query", "").strip()
        broadcaster_id = request.form.get("broadcaster_id")

        if not query:
            return jsonify({"status": "error", "message": "Search query is required"}), 400

        # Sanitize the query - only allow letters, numbers, spaces, hyphens, and underscores
        import re
        sanitized_query = re.sub(r'[^a-zA-Z0-9\s_-]', '', query)
        sanitized_query = sanitized_query.strip()

        if not sanitized_query:
            return jsonify({"status": "error", "message": "Search query contains no valid characters"}), 400

        return text_search_content_internal(sanitized_query, broadcaster_id)

    except Exception as e:
        logger.error(f"Error in text search: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


def text_search_content_internal(query, broadcaster_id):
    """Internal function to perform text search"""
    from app.models.content_queue import Content, ContentQueueSubmission
    from sqlalchemy import or_, and_

    # Get allowed broadcasters
    if not broadcaster_id:
        if UserService.has_permission(current_user, [PermissionType.Admin, PermissionType.Moderator]):
            broadcasters = BroadcasterService.get_all(show_hidden=True)
        else:
            if UserService.is_broadcaster(current_user):
                broadcasters = [UserService.get_broadcaster(current_user)]
            broadcasters += BroadcasterService.get_all(show_hidden=False)
        broadcaster_ids = [broadcaster.id for broadcaster in broadcasters]
    else:
        broadcaster_ids = [int(broadcaster_id)]

    # Build text search query
    search_conditions = []

    # Search in content title and channel name
    search_conditions.append(Content.title.ilike(f"%{query}%"))
    search_conditions.append(Content.channel_name.ilike(f"%{query}%"))

    # Search in user comments from submissions
    search_conditions.append(
        ContentQueueSubmission.user_comment.ilike(f"%{query}%")
    )

    # Search in submitter usernames
    search_conditions.append(
        Users.name.ilike(f"%{query}%")
    )

    # Execute search query with joins
    queue_items = db.session.execute(
        select(ContentQueue)
        .join(Content, ContentQueue.content_id == Content.id)
        .join(ContentQueueSubmission, ContentQueue.id == ContentQueueSubmission.content_queue_id)
        .join(Users, ContentQueueSubmission.user_id == Users.id)
        .filter(
            and_(
                ContentQueue.broadcaster_id.in_(broadcaster_ids),
                or_(*search_conditions)
            )
        )
        .distinct()
    ).scalars().all()

    if queue_items:
        return render_template("management_items.html",
                               queue_items=queue_items,
                               total_items=len(queue_items),
                               total_pages=1,
                               page=1,
                               search_query=query)
    else:
        return f"<div class='alert alert-info'>No content found matching '{query}'.</div>"


@clip_queue_blueprint.route("/default_weight_settings", methods=["GET"])
@login_required
@require_permission()
def get_default_weight_settings():
    """Get default weight settings form HTML after reset"""
    try:
        broadcaster = UserService.get_broadcaster(current_user)
        if not broadcaster:
            logger.error("Broadcaster not found")
            return jsonify({"status": "error", "message": "Broadcaster not found"}), 404

        # Reset to defaults first
        WeightSettingsService.reset_weight_settings(broadcaster.id)
        
        # Get the default settings
        default_settings = WeightSettingsService.get_default_weight_settings()
        
        # Return the weight settings form HTML with default values
        return render_template("weight_settings_form.html", weight_settings=default_settings)
    except Exception as e:
        logger.error(f"Error getting default weight settings: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@clip_queue_blueprint.route("/reset_weight_settings", methods=["POST"])
@login_required
@require_permission()
def reset_weight_settings():
    """Reset weight settings to defaults"""
    try:
        broadcaster = UserService.get_broadcaster(current_user)
        if not broadcaster:
            logger.error("Broadcaster not found")
            return jsonify({"status": "error", "message": "Broadcaster not found"}), 404

        WeightSettingsService.reset_weight_settings(broadcaster.id)
        
        return jsonify({
            "status": "success",
            "message": "Weight settings reset to defaults"
        })
    except Exception as e:
        logger.error(f"Error resetting weight settings: {e}")
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


@clip_queue_blueprint.route("/weight_settings_preview", methods=["POST"])
@login_required
@require_permission()
def weight_settings_preview():
    """Generate preview of how weight settings affect queue ordering"""
    try:
        broadcaster = UserService.get_broadcaster(current_user)
        if not broadcaster:
            return jsonify({"status": "error", "message": "Broadcaster not found"}), 404

        # Parse weight settings from request
        from app.models.content_queue_settings import WeightSettings
        
        weight_data = {}
        
        # Boolean fields
        for field in ['prefer_shorter', 'keep_fresh', 'ignore_popularity', 'boost_variety', 'viewer_priority']:
            weight_data[field] = field in request.form
        
        # Float fields (intensity settings)
        for field in ['prefer_shorter_intensity', 'keep_fresh_intensity', 'ignore_popularity_intensity', 
                     'boost_variety_intensity', 'viewer_priority_intensity']:
            if field in request.form:
                try:
                    weight_data[field] = float(request.form[field])
                except (ValueError, TypeError):
                    weight_data[field] = 0.5  # default
        
        # Integer fields (advanced settings)
        for field in ['short_clip_threshold_seconds', 'freshness_window_minutes']:
            if field in request.form:
                try:
                    weight_data[field] = int(request.form[field])
                except (ValueError, TypeError):
                    weight_data[field] = 60 if 'threshold' in field else 30  # defaults
        
        # Create preview weight settings
        try:
            preview_settings = WeightSettings(**weight_data)
            logger.debug(f"Preview weight settings: {weight_data}")
        except Exception as e:
            logger.error(f"Error creating preview settings: {e}")
            preview_settings = WeightSettings()  # use defaults
        
        # Check if user has enough real queue items (5+)
        real_queue_items = get_content_queue(broadcaster.id, include_watched=False, include_skipped=False)
        
        if len(real_queue_items) >= 5:
            # Use real queue items and apply weight settings to show ordering
            preview_items, item_scores = apply_weight_settings_to_items(real_queue_items, preview_settings)
            use_real_data = True
        else:
            # Generate fake queue items for preview
            preview_items = generate_fake_queue_items(preview_settings)
            item_scores = {}
            use_real_data = False
        
        return render_template(
            "weight_settings_preview.html",
            preview_items=preview_items,
            weight_settings=preview_settings,
            use_real_data=use_real_data,
            item_scores=item_scores if use_real_data else {},
            broadcaster=broadcaster,
            is_user_trusted=is_user_trusted
        )
    except Exception as e:
        logger.error(f"Error generating weight settings preview: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


def apply_weight_settings_to_items(queue_items, weight_settings):
    """Apply weight settings to real queue items and return sorted list"""
    from app.services.content_queue import WeightSettingsService
    from datetime import datetime, timezone
    
    # Calculate priority scores for each item using the preview weight settings
    scored_items = []
    for item in queue_items:
        try:
            # Calculate age in minutes
            if item.submissions:
                earliest_submission = min(item.submissions, key=lambda s: s.submitted_at)
                submitted_at = earliest_submission.submitted_at
                
                # Handle timezone-aware vs timezone-naive datetime comparison
                if submitted_at.tzinfo is None:
                    # If submitted_at is naive, assume it's UTC and make it aware
                    submitted_at = submitted_at.replace(tzinfo=timezone.utc)
                
                age_minutes = int((datetime.now(timezone.utc) - submitted_at).total_seconds() / 60)
            else:
                age_minutes = 0
            
            # Get submission count (popularity) - use total weight instead of just count
            if item.submissions:
                base_popularity = sum(sub.weight for sub in item.submissions)
            else:
                base_popularity = 1.0
            
            # Get duration
            duration_seconds = item.content.duration if item.content.duration else 0
            
            # Check if submitter is trusted (VIP/MOD/Owner)
            is_trusted = False
            if item.submissions and len(item.submissions) > 0:
                # Get broadcaster_id from the item
                broadcaster_id = item.broadcaster_id
                # Check if any submitter has VIP/MOD/Owner role for this broadcaster
                is_trusted = any(
                    is_user_trusted(sub.user_id, broadcaster_id) 
                    for sub in item.submissions
                )
            
            logger.debug(f"Item {item.id}: popularity={base_popularity}, age={age_minutes}, duration={duration_seconds}, trusted={is_trusted}")
            
            # Calculate score using the same logic as the main queue
            score, _ = WeightSettingsService.calculate_score(
                weight_settings, base_popularity, age_minutes, duration_seconds, is_trusted
            )
            logger.debug(f"Calculated score for item {item.id}: {score}")
            scored_items.append((item, score))
        except Exception as e:
            # If scoring fails, give it a default score
            logger.error(f"Error calculating score for item {item.id}: {e}")
            scored_items.append((item, 0.0))
    
    # Sort by score (highest first) and return items with scores
    scored_items.sort(key=lambda x: x[1], reverse=True)
    
    # Return top 10 items for preview and their scores
    top_items = scored_items[:10]
    items = [item for item, score in top_items]
    scores = {item.id: score for item, score in top_items}
    
    return items, scores


def generate_fake_queue_items(weight_settings):
    """Generate fake queue items to demonstrate weight settings effects"""
    import random
    from datetime import datetime, timedelta
    
    # Sample data for fake items
    titles = [
        "Amazing clutch play in ranked!",
        "Funny moment with chat",
        "Epic fail compilation",
        "New world record attempt",
        "Reacting to viral video",
        "Speedrun practice session",
        "Viewer game suggestion",
        "Late night gaming session",
        "Tutorial: Advanced techniques",
        "Collab stream highlights"
    ]
    
    channels = [
        "TopStreamer", "GamingGuru", "ChatMaster", "ProPlayer", "FunnyGamer",
        "SpeedRunner", "ReactQueen", "TutorialKing", "CollabCentral", "NightOwl"
    ]
    
    platforms = ["YouTube", "Twitch"]
    
    fake_items = []
    base_time = datetime.now(timezone.utc)
    
    for i in range(15):  # Generate 15 fake items
        # Vary the submission times
        age_minutes = random.randint(1, 180)  # 1 to 180 minutes ago
        submitted_at = base_time - timedelta(minutes=age_minutes)
        
        # Vary durations
        duration_seconds = random.choice([30, 45, 60, 90, 120, 180, 240, 300, 420, 600])
        
        # Vary popularity (number of submissions)
        popularity = random.choice([1, 1, 1, 2, 2, 3, 4, 5])  # Weighted toward lower values
        
        # Random channel (for variety testing)
        channel = random.choice(channels)
        
        # Some users are "trusted" (VIP/MOD)
        is_trusted = random.choice([True, False, False])  # 1/3 chance
        
        # Calculate frequency of this channel in the queue
        channel_frequency = sum(1 for item in fake_items if item.get('channel') == channel) + 1
        
        # Calculate score using weight settings
        final_score, breakdown = WeightSettingsService.calculate_score(
            weight_settings=weight_settings,
            base_popularity=popularity,
            age_minutes=age_minutes,
            duration_seconds=duration_seconds,
            is_trusted=is_trusted
        )
        
        # Format age properly
        if age_minutes < 60:
            age_formatted = f"{age_minutes:.0f}m"
        elif age_minutes < 1440:  # 24 hours
            age_formatted = f"{age_minutes/60:.1f}h"
        else:
            age_formatted = f"{age_minutes/1440:.1f}d"
        
        fake_item = {
            'id': f'fake_{i}',
            'title': random.choice(titles),
            'channel': channel,
            'platform': random.choice(platforms),
            'duration_seconds': duration_seconds,
            'duration_formatted': f"{duration_seconds//60}:{duration_seconds%60:02d}",
            'popularity': popularity,
            'age_minutes': age_minutes,
            'age_formatted': age_formatted,
            'is_trusted': is_trusted,
            'channel_frequency': channel_frequency,
            'final_score': final_score,
            'breakdown': breakdown,
            'submitted_at': submitted_at
        }
        
        fake_items.append(fake_item)
    
    # Sort by final score (descending)
    fake_items.sort(key=lambda x: x['final_score'], reverse=True)
    
    return fake_items
