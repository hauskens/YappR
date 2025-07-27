from flask import Blueprint, render_template, jsonify, flash, redirect, request, url_for
from app.logger import logger
from flask_login import current_user, login_required  # type: ignore
from datetime import datetime, timedelta, timezone
from app.models import db
from app.models.enums import PermissionType
from app.models.content_queue_settings import ContentQueueSettings
from app.models.content_queue import ContentQueue, ContentQueueSubmission
from app.models.user import ExternalUser, ExternalUserWeight
from app.platforms.handler import PlatformRegistry
from app.retrievers import get_content_queue
from app.services.broadcaster import BroadcasterService
from app.permissions import require_permission
from app.content_queue import clip_score
from flask_socketio import SocketIO
import random
from sqlalchemy import select
from app.rate_limit import limiter

socketio = SocketIO()

clip_queue_blueprint = Blueprint(
    'clip_queue', __name__, url_prefix='/clip_queue', template_folder='templates', static_folder='static')


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
            logger.info("Loading clip queue", extra={
                        "user_id": current_user.id})
            broadcaster = BroadcasterService.get_by_external_id(
                current_user.external_account_id)
            if broadcaster is None:
                return render_template("promo.html")
            queue_items = get_content_queue(broadcaster.id)
            if broadcaster.last_active() is None or broadcaster.last_active() < datetime.now() - timedelta(minutes=10):
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
        broadcaster = BroadcasterService.get_by_external_id(
            current_user.external_account_id)
        if broadcaster is None:
            return jsonify({"error": "Broadcaster not found"}), 404
        if broadcaster_id != broadcaster.id:
            return jsonify({"error": "You do not have permission to mark this clip as watched"}), 403

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
        if broadcaster is None:
            return jsonify({"error": "Broadcaster not found"}), 404
        if broadcaster_id != broadcaster.id:
            return jsonify({"error": "You do not have permission to skip this clip"}), 403
        if queue_item.skipped:
            logger.info("Unskipping clip", extra={
                        "queue_item_id": queue_item.id, "user_id": current_user.id})
            queue_item.skipped = False
        else:
            logger.info("Skipping clip", extra={
                        "queue_item_id": queue_item.id, "user_id": current_user.id})
            queue_item.skipped = True
        db.session.commit()
        socketio.emit(
            "queue_update",
            to=f"queue-{queue_item.broadcaster_id}",
        )
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
    logger.info("Loading clip queue items")
    try:
        # Check if we should show history (watched clips)
        show_history = request.args.get(
            'show_history', 'false').lower() == 'true'

        # Get broadcaster and content queue settings
        broadcaster = BroadcasterService.get_by_external_id(
            current_user.external_account_id)

        # Get prefer_shorter_content setting from database
        queue_settings = db.session.execute(
            select(ContentQueueSettings).filter(
                ContentQueueSettings.broadcaster_id == broadcaster.id
            )
        ).scalars().one_or_none()

        prefer_shorter = False  # Default value
        if queue_settings:
            prefer_shorter = queue_settings.prefer_shorter_content

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
            if channel.platform.name.lower() == "twitch" and channel.settings.content_queue_enabled:
                queue_enabled = True
                break
        if broadcaster is not None and queue_enabled:
            # Include watched and skipped clips if show_history is True
            queue_items = get_content_queue(
                broadcaster.id, include_watched=show_history, include_skipped=show_history)

            # Filter out rickroll if not active and not admin/mod
            if (broadcaster.last_active() is None or broadcaster.last_active() < datetime.now() - timedelta(minutes=10)) and not current_user.has_permission(["mod", "admin"]):
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
                    any(search_query.lower() in submission.user.username.lower()
                        for submission in item.submissions)
                ]

            # Sort items - for history tab, we might want to sort differently
            now = datetime.now(timezone.utc)
            if show_history:
                # For history, sort by watched_at time (most recent first)
                queue_items = sorted(
                    queue_items, key=lambda item: item.watched_at if item.watched_at else datetime.min, reverse=True)
            else:
                # For upcoming queue, sort by score
                queue_items.sort(key=lambda item: clip_score(
                    item, now=now, prefer_shorter=prefer_shorter), reverse=True)

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
# @require_permission(require_broadcaster=True, broadcaster_id_param="broadcaster_id", require_moderator=True)
def penalty_external_user(broadcaster_id: int, external_user_id: int):
    standard_penalty = 0.2
    standard_ban_duration = 7
    force_ban = request.args.get('ban', 'false').lower() == 'true'

    try:
        external_user_weight = db.session.query(ExternalUserWeight).filter_by(
            external_user_id=external_user_id, broadcaster_id=broadcaster_id).one_or_none()
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
            logger.info(f"Force banning user {external_user_id}", extra={
                        "user_id": current_user.id})
            external_user_weight.weight = 0
            external_user_weight.banned = True
            external_user_weight.banned_at = datetime.now()
            external_user_weight.unban_at = datetime.now(
            ) + timedelta(days=standard_ban_duration)
        else:
            # Apply standard penalty
            external_user_weight.weight = round(
                external_user_weight.weight - standard_penalty, 2)
            if external_user_weight.weight <= 0:
                external_user_weight.weight = 0
                external_user_weight.banned = True
                external_user_weight.banned_at = datetime.now()
                external_user_weight.unban_at = datetime.now(
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
# @require_permission(require_broadcaster=True, broadcaster_id_param="broadcaster_id", require_moderator=True)
@require_permission()
def reset_external_user_penalties(broadcaster_id: int, external_user_id: int):
    logger.info("Resetting external user penalties", extra={
                "broadcaster_id": broadcaster_id, "external_user_id": external_user_id})
    try:
        # Get the external user
        external_user = db.session.query(
            ExternalUser).filter_by(id=external_user_id).one()

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
        logger.error("Error resetting penalties for external user %s: %s",
                     external_user_id, e, extra={"user_id": current_user.id})
        db.session.rollback()
        flash("An error occurred while resetting penalties.", "danger")

        # In case of error, try to get data for the template
        try:
            external_user = db.session.query(
                ExternalUser).filter_by(id=external_user_id).one()
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


@clip_queue_blueprint.route("/settings", methods=["GET", "POST"])
@login_required
@require_permission()
def settings():
    """Get allowed platforms for the broadcaster's queue"""
    try:
        broadcaster = current_user.get_broadcaster()
        if not broadcaster:
            logger.error("Broadcaster not found")
            return jsonify({"status": "error", "message": "Broadcaster not found"}), 404

        if request.method == "POST":
            # Get selected platforms from form
            platforms = request.form.getlist("platforms")
            # Get prefer_shorter_content preference
            prefer_shorter = "prefer_shorter_content" in request.form

            logger.info(f"Updating queue settings", extra={
                "broadcaster_id": broadcaster.id,
                "platforms": platforms,
                "prefer_shorter_content": prefer_shorter
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
            db.session.commit()

            return jsonify({
                "status": "success",
                "message": "Platform settings updated successfully"
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

            return jsonify({
                "status": "success",
                "platforms": platforms,
                "prefer_shorter_content": prefer_shorter
            })
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
        if current_user.has_permission([PermissionType.Admin, PermissionType.Moderator]):
            broadcasters = BroadcasterService.get_all(show_hidden=True)
        else:
            if current_user.is_broadcaster():
                broadcasters = [current_user.get_broadcaster()]
            broadcasters += BroadcasterService.get_all(show_hidden=False)
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
                    username=current_user.name,
                    external_user_id=current_user.external_account_id,
                    submission_source_type=ContentQueueSubmissionSource.Web,
                    submission_source_id=0,
                    submission_weight=1.0,
                    twitch_client=twitch_client
                )

            queue_item_id = asyncio.run(add_content_async())

            if queue_item_id:
                queue_item = db.session.query(ContentQueue).filter(
                    ContentQueue.id == queue_item_id).one()
                return render_template("management_items.html",
                                       queue_items=[queue_item],
                                       total_items=1,
                                       total_pages=1,
                                       page=1,
                                       search_query="")
            else:
                return jsonify({"status": "error", "message": "Failed to add content or content not supported"})

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
                    if current_user.has_permission([PermissionType.Admin, PermissionType.Moderator]):
                        broadcasters = BroadcasterService.get_all(show_hidden=True)
                    else:
                        if current_user.is_broadcaster():
                            broadcasters = [current_user.get_broadcaster()]
                        broadcasters += BroadcasterService.get_all(show_hidden=False)
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
        if current_user.has_permission([PermissionType.Admin, PermissionType.Moderator]):
            broadcasters = BroadcasterService.get_all(show_hidden=True)
        else:
            if current_user.is_broadcaster():
                broadcasters = [current_user.get_broadcaster()]
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
    from app.models.user import ExternalUser
    search_conditions.append(
        ExternalUser.username.ilike(f"%{query}%")
    )

    # Execute search query with joins
    queue_items = db.session.execute(
        select(ContentQueue)
        .join(Content, ContentQueue.content_id == Content.id)
        .join(ContentQueueSubmission, ContentQueue.id == ContentQueueSubmission.content_queue_id)
        .join(ExternalUser, ContentQueueSubmission.user_id == ExternalUser.id)
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
