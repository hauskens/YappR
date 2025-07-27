from flask import Blueprint, render_template, redirect, request, url_for, flash
from app.permissions import require_permission
from app.models import db
from app.models import (
    Platforms,
    VideoType,
    PermissionType,
    AccountSource,
    Broadcaster,
    ChannelSettings,
    Channels,
    ChannelModerator,
    BroadcasterSettings,
    ContentQueue,
    ContentQueueSubmission,
    ContentQueueSubmissionSource,
    Content,
    ExternalUser,
)
from app.services import BroadcasterService
from app.cache import cache, make_cache_key
from app.logger import logger
from flask_login import current_user, login_required  # type: ignore
from datetime import datetime
from app.retrievers import get_platforms

broadcaster_blueprint = Blueprint(
    'broadcaster', __name__, url_prefix='/broadcaster', template_folder='templates', static_folder='static')


@broadcaster_blueprint.route("")
@login_required
@require_permission()
@cache.memoize(timeout=60)
def broadcasters():
    broadcasters = BroadcasterService.get_all()
    logger.info("Loaded broadcasters.html")
    return render_template("broadcasters.html", broadcasters=broadcasters)


@broadcaster_blueprint.route("/delete/<int:broadcaster_id>", methods=["GET"])
@login_required
@require_permission(require_broadcaster=True, broadcaster_id_param="broadcaster_id", permissions=PermissionType.Admin)
def broadcaster_delete(broadcaster_id: int):
    logger.warning("Attempting to delete broadcaster %s", broadcaster_id)
    logger.info("Deleting broadcaster %s", broadcaster_id)
    BroadcasterService.delete(broadcaster_id)
    return redirect(url_for("broadcasters"))


@broadcaster_blueprint.route("/create", methods=["POST", "GET"])
@login_required
@require_permission()
@cache.cached(timeout=60, make_cache_key=make_cache_key)
def broadcaster_create():
    if request.method == "GET":
        logger.info("Loaded broadcaster_add.html")
        return render_template("broadcaster_add.html")
    elif request.method == "POST":
        try:
            name = request.form["name"]
            hidden = "hidden" in request.form
            channel_id = request.form.get("channel_id", "")
            channel_name = request.form.get("channel_name", "")
            twitch_channel = request.form.get("twitch_channel", "")
            willbehave = "willbehave" in request.form

            logger.info(
                "Creating new broadcaster: %s for twitch channel: %s", name, twitch_channel)
            if not willbehave:
                flash("You must agree to the terms", "danger")
                logger.warning(
                    "Denied adding broadcaster %s - user did not agree to terms", name)
                return render_template("broadcaster_add.html", form=request.form)

            if not twitch_channel:
                flash("You must select a Twitch channel", "danger")
                logger.warning(
                    "Denied adding broadcaster %s - no twitch channel selected", name)
                return render_template("broadcaster_add.html", form=request.form)

            existing_broadcasters = BroadcasterService.get_all()
            for broadcaster in existing_broadcasters:
                if broadcaster.name.lower() == name.lower():
                    flash("This broadcaster already exists", "error")
                    logger.warning(
                        "Adding broadcaster %s failed - broadcaster already exists", name)
                    return render_template(
                        "broadcaster_add.html",
                        form=request.form
                    )

            # Create the new broadcaster
            new_broadcaster = Broadcaster(name=name, hidden=hidden)
            db.session.add(new_broadcaster)
            db.session.flush()

            # Get the platform ID for Twitch
            twitch_platform = db.session.query(
                Platforms).filter_by(name="Twitch").one()
            # Create a channel for this broadcaster
            new_channel = Channels(
                name=name,
                broadcaster_id=new_broadcaster.id,
                platform_id=twitch_platform.id,
                platform_ref=channel_name,
                platform_channel_id=channel_id,
                main_video_type=VideoType.VOD.name,
            )
            db.session.add(new_channel)
            db.session.flush()

            # Handle channel settings (Twitch bot settings)
            content_queue_enabled = 'content_queue_enabled' in request.form
            chat_collection_enabled = 'chat_collection_enabled' in request.form or content_queue_enabled

            if chat_collection_enabled or content_queue_enabled:
                channel_settings = ChannelSettings(
                    channel_id=new_channel.id,
                    chat_collection_enabled=chat_collection_enabled,
                    content_queue_enabled=content_queue_enabled
                )
                db.session.add(channel_settings)
                logger.info("Added initial channel settings - chat collection: %s, content queue: %s",
                            chat_collection_enabled, content_queue_enabled)

            # Handle broadcaster settings (Discord bot settings)
            discord_channel_id = request.form.get('discord_channel_id')
            if discord_channel_id:
                broadcaster_settings = BroadcasterSettings(
                    broadcaster_id=new_broadcaster.id,
                    linked_discord_channel_id=int(
                        discord_channel_id) if discord_channel_id else None
                )
                db.session.add(broadcaster_settings)
                logger.info(
                    "Added initial broadcaster settings - Discord channel ID: %s", discord_channel_id)

            if channel_id != current_user.external_account_id:
                db.session.add(
                    ChannelModerator(
                        channel_id=new_broadcaster.id,
                        user_id=current_user.id,
                    )
                )
            db.session.commit()

            intro_clip = db.session.query(Content).filter_by(
                url="https://www.youtube.com/watch?v=dQw4w9WgXcQ").one_or_none()
            if intro_clip:
                external_user = db.session.execute(
                    select(ExternalUser).filter(
                        ExternalUser.username == "hauskens",
                        ExternalUser.account_type == AccountSource.Twitch,
                    )
                ).scalars().one_or_none()
                if external_user:

                    # Add to content queue
                    queue_item = ContentQueue(
                        broadcaster_id=new_broadcaster.id,
                        content_id=intro_clip.id,
                    )
                    db.session.add(queue_item)
                    db.session.flush()  # Flush to get the queue item ID
                    logger.debug("Added intro clip to content queue, tomfoolery", extra={
                                 "broadcaster_id": new_broadcaster.id, "queue_item_id": queue_item.id})

                    # Create submission record
                    submission = ContentQueueSubmission(
                        content_queue_id=queue_item.id,
                        content_id=intro_clip.id,
                        user_id=external_user.id,
                        submitted_at=datetime.now(),
                        submission_source_type=ContentQueueSubmissionSource.Twitch,
                        submission_source_id=external_user.id,
                        weight=69,
                        user_comment="lmao gottem"
                    )
                    db.session.add(submission)

                # Commit all changes
                db.session.commit()
            flash(f"Broadcaster '{name}' was successfully created", "success")
            logger.info("Broadcaster %s was successfully created",
                        name, extra={"broadcaster_id": new_broadcaster.id})
            return redirect(url_for("broadcaster_edit", id=new_broadcaster.id))
        except Exception as e:
            flash(f"Failed to create broadcaster", "danger")
            logger.error("Failed to create broadcaster %s: %s", name, e)
            return redirect(url_for("broadcaster_add"))


@broadcaster_blueprint.route("/edit/<int:id>", methods=["GET"])
@login_required
@require_permission()
@cache.cached(timeout=10, make_cache_key=make_cache_key)
def broadcaster_edit(id: int):
    broadcaster = BroadcasterService.get_by_id(id)
    logger.info("Loaded broadcaster_edit.html", extra={
                "broadcaster_id": broadcaster.id})
    return render_template(
        "broadcaster_edit.html",
        broadcaster=broadcaster,
        channels=broadcaster.channels,
        platforms=get_platforms(),
        video_types=VideoType,
    )


@broadcaster_blueprint.route("/<int:broadcaster_id>/create_clip", methods=["POST"])
@login_required
def broadcaster_create_clip(broadcaster_id: int):
    # Check if user has permission to modify this broadcaster
    logger.info("Attempting to create clip for broadcaster",
                extra={"broadcaster_id": broadcaster_id})
    if current_user.is_anonymous or not (current_user.broadcaster_id == broadcaster_id or current_user.has_permission(["admin"])):
        logger.error("User does not have permission to create clip for broadcaster", extra={
                     "broadcaster_id": broadcaster_id})
        return "You do not have permission to modify this broadcaster", 403

    # Add clip creation task to Redis queue
    from app import redis_task_queue
    task_id = redis_task_queue.enqueue_clip_creation(str(broadcaster_id))

    if task_id:
        flash("Clip creation task queued successfully")
        logger.info("Clip creation task %s queued for broadcaster", task_id, extra={
                    "broadcaster_id": broadcaster_id, "user_id": current_user.id})
    else:
        flash("Failed to queue clip creation task", "error")
        logger.error("Failed to queue clip creation task for broadcaster", extra={
                     "broadcaster_id": broadcaster_id, "user_id": current_user.id})

    return redirect(request.referrer)


@broadcaster_blueprint.route("/<int:broadcaster_id>/settings/update", methods=["POST"])
@login_required
@require_permission(permissions=[PermissionType.Admin], require_broadcaster=True, broadcaster_id_param="broadcaster_id", check_banned=True)
def broadcaster_settings_update(broadcaster_id: int):
    settings = db.session.query(BroadcasterSettings).filter_by(
        broadcaster_id=broadcaster_id).first()
    if not settings:
        settings = BroadcasterSettings(broadcaster_id=broadcaster_id)
        db.session.add(settings)

    discord_channel_id = request.form.get('discord_channel_id')
    settings.linked_discord_channel_id = int(
        discord_channel_id) if discord_channel_id else None

    logger.info("Updating broadcaster settings, linked discord channel id: %s",
                discord_channel_id, extra={"dcaster_id": broadcaster_id, "user_id": current_user.id})

    # Update broadcaster hidden status (admin only)
    if current_user.has_permission([PermissionType.Admin]) and request.form.get('hidden') is not None:
        broadcaster = db.session.query(
            Broadcaster).filter_by(id=broadcaster_id).first()
        if broadcaster:
            broadcaster.hidden = 'hidden' in request.form
            logger.info("Updating broadcaster hidden status, hidden: %s", 'hidden' in request.form, extra={
                        "broadcaster_id": broadcaster_id, "user_id": current_user.id})

    db.session.commit()

    # Check if this is an HTMX request
    if request.headers.get('HX-Request'):
        # Return success message for HTMX
        return '<div class="alert alert-success">Settings updated successfully</div>'
    else:
        flash('Broadcaster settings updated successfully')
        return redirect(request.referrer)
