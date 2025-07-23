from flask import Blueprint, render_template, request
from app.logger import logger
from flask_login import current_user, login_required  # type: ignore
from app.permissions import require_permission
from app.models.db import PermissionType, db, Broadcaster
from app.retrievers import get_bots, get_broadcasters, get_moderated_channels, get_broadcaster, get_content_queue
from datetime import datetime, timedelta, timezone

management_blueprint = Blueprint(
    'management', __name__, url_prefix='/management', template_folder='templates', static_folder='static')


@management_blueprint.route("")
@login_required
@require_permission()
def management():
    logger.info("Loaded management.html")
    moderated_channels = get_moderated_channels(current_user.id)
    bots = None
    if current_user.has_permission(PermissionType.Admin):
        bots = get_bots()
        broadcasters = get_broadcasters(show_hidden=True)

    elif moderated_channels is not None or current_user.is_broadcaster():
        # Convert moderated channels to a list of broadcasters
        broadcaster_ids = [
            channel.channel.broadcaster_id for channel in moderated_channels]
        if current_user.is_broadcaster():
            broadcaster_ids.append(current_user.get_broadcaster().id)
        broadcasters = db.session.query(Broadcaster).filter(
            Broadcaster.id.in_(broadcaster_ids)).all()

    if moderated_channels is None and not (current_user.has_permission(PermissionType.Admin) or current_user.is_broadcaster()):
        return "You do not have access", 403

    broadcaster_id = request.args.get('broadcaster_id', type=int)
    if broadcaster_id is None and current_user.is_broadcaster():
        broadcaster_id = current_user.get_broadcaster().id

    logger.info(f"User is accessing management page",
                extra={"broadcaster_id": broadcaster_id})
    return render_template(
        "management.html", bots=bots, broadcasters=broadcasters, selected_broadcaster_id=broadcaster_id
    )


@management_blueprint.route("/items")
@login_required
def management_items():
    logger.info("Loading management items with htmx")
    try:
        # Get filter parameters from request
        broadcaster_id = request.args.get('broadcaster_id', type=int)
        sort_by = request.args.get('sort_by', 'newest')

        # Pagination parameters
        page = request.args.get('page', 1, type=int)
        # Default: show 20 items per page
        per_page = request.args.get('per_page', 20, type=int)

        # Search parameter
        search_query = request.args.get('search', '').strip()

        # Handle checkbox values - checkboxes only send values when checked
        show_watched_param = request.args.get('show_watched')
        show_skipped_param = request.args.get('show_skipped')

        # Convert to boolean - 'false' string should be treated as False
        show_watched = show_watched_param != 'false' if show_watched_param is not None else False
        show_skipped = show_skipped_param != 'false' if show_skipped_param is not None else False

        # Debug log the received parameters
        logger.debug(
            f"Filter params: broadcaster_id={broadcaster_id}, sort_by={sort_by}, show_watched={show_watched}, show_skipped={show_skipped}, page={page}, search={search_query}")
        logger.debug(f"All request args: {request.args}")

        # If no broadcaster_id is provided and user is a broadcaster, use their broadcaster_id
        if broadcaster_id is None and current_user.is_broadcaster():
            broadcaster_id = current_user.get_broadcaster().id

        if broadcaster_id is not None:
            broadcaster = get_broadcaster(broadcaster_id)
            if broadcaster is None:
                return "Broadcaster not found", 404

        # Get queue items with filters
        queue_items = get_content_queue(
            broadcaster_id,
            include_watched=show_watched,
            include_skipped=show_skipped
        )
        if (broadcaster.last_active() is None or broadcaster.last_active() < datetime.now() - timedelta(minutes=10)) and not current_user.has_permission(["mod", "admin"]):
            queue_items = [item for item in queue_items if item.content.url !=
                           "https://www.youtube.com/watch?v=dQw4w9WgXcQ"]

        # Apply search filter if provided
        if search_query:
            queue_items = [
                item for item in queue_items if
                search_query.lower() in item.content.title.lower() or
                search_query.lower() in item.content.channel_name.lower() or
                any(search_query.lower() in submission.user.username.lower() for submission in item.submissions) or
                any(submission.user_comment and search_query.lower(
                ) in submission.user_comment.lower() for submission in item.submissions)
            ]

        # Apply sorting
        if sort_by == 'oldest':
            # Sort by oldest first (based on first submission date)
            queue_items = sorted(queue_items, key=lambda x: min(
                s.submitted_at for s in x.submissions) if x.submissions else datetime.now())
        elif sort_by == 'most_submitted':
            # Sort by number of submissions (most first)
            queue_items = sorted(queue_items, key=lambda x: len(
                x.submissions), reverse=True)
        else:  # 'newest' is default
            # Sort by newest first (based on first submission date)
            queue_items = sorted(queue_items, key=lambda x: min(
                s.submitted_at for s in x.submissions) if x.submissions else datetime.now(), reverse=True)

        # Calculate pagination metadata
        total_items = len(queue_items)
        total_pages = (total_items + per_page -
                       1) // per_page  # Ceiling division

        # Ensure page number is valid
        if page < 1:
            page = 1
        elif page > total_pages and total_pages > 0:
            page = total_pages

        # Apply pagination
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_items = queue_items[start_idx:end_idx]

        logger.info("Successfully loaded management items", extra={
            "broadcaster_id": broadcaster_id,
            "queue_items": len(paginated_items),
            "total_items": total_items,
            "page": page,
            "total_pages": total_pages,
            "filters": {"show_watched": show_watched, "show_skipped": show_skipped, "sort_by": sort_by, "search": search_query}
        })

        return render_template(
            "management_items.html",
            queue_items=paginated_items,
            selected_broadcaster_id=broadcaster_id,
            now=datetime.now(),
            page=page,
            per_page=per_page,
            total_items=total_items,
            total_pages=total_pages,
            search_query=search_query,
            management=True
        )
    except Exception as e:
        logger.error("Error loading management items: %s", e)
        return "Error loading management items", 500
