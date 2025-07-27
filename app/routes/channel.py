from flask import Blueprint, render_template, redirect, request, flash
from app.logger import logger
from flask_login import current_user, login_required  # type: ignore
from app.permissions import require_permission
from app.models import db
from app.models.channel import Channels
from app.models.video import VideoType
from app.models.enums import PermissionType
from app.models.channel import ChannelSettings
from app.retrievers import get_platforms, get_channel, get_stats_videos_with_audio, get_stats_videos_with_good_transcription
from app.services.broadcaster import BroadcasterService
from app.rate_limit import limiter, rate_limit_exempt
from app.cache import cache, make_cache_key


channel_blueprint = Blueprint('channel', __name__, url_prefix='/channel',
                              template_folder='templates', static_folder='static')


@channel_blueprint.route("/create", methods=["POST"])
@login_required
# TODO: expand permission check
@require_permission()
def channel_create():
    name = request.form["name"]
    broadcaster_id = int(request.form["broadcaster_id"])
    platform_id = int(request.form["platform_id"])
    platform_ref = request.form["platform_ref"]
    channel_type = request.form["channel_type"]
    channel_id = request.form.get("channel_id", None)
    logger.info("Creating new channel: %s for broadcaster: %s", name,
                broadcaster_id, extra={"broadcaster_id": broadcaster_id})
    new_channel = Channels(
        name=name,
        broadcaster_id=broadcaster_id,
        platform_id=platform_id,
        platform_ref=platform_ref,
        main_video_type=channel_type,
        platform_channel_id=channel_id,
    )
    db.session.add(new_channel)
    db.session.commit()
    logger.info("Channel %s was successfully created", name, extra={
                "channel_id": new_channel.id, "broadcaster_id": broadcaster_id})
    return render_template(
        "broadcaster_edit.html",
        broadcaster=BroadcasterService.get_by_id(broadcaster_id),
        channels=BroadcasterService.get_channels(broadcaster_id=broadcaster_id),
        platforms=get_platforms(),
        video_types=VideoType,
    )


@channel_blueprint.route("/<int:channel_id>/link", methods=["POST"])
@login_required
@require_permission(permissions=PermissionType.Admin)
def channel_link(channel_id: int):
    try:
        link_channel_id = int(request.form["link_channel_id"])
    except:
        link_channel_id = None
    logger.info("Linking channel to %s", link_channel_id,
                extra={"channel_id": channel_id})
    _ = get_channel(channel_id).link_to_channel(link_channel_id)
    return redirect(request.referrer)


@channel_blueprint.route("/<int:channel_id>/look_for_linked")
@login_required
@require_permission(permissions=PermissionType.Admin)
def channel_look_for_linked(channel_id: int):
    channel = get_channel(channel_id)
    logger.info("Looking for linked videos for channel",
                extra={"channel_id": channel_id})
    # channel.look_for_linked_videos()
    channel.update_thumbnail()
    return redirect(request.referrer)


@channel_blueprint.route("/<int:channel_id>/delete")
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def channel_delete(channel_id: int):
    logger.warning("Deleting channel", extra={"channel_id": channel_id})
    channel = get_channel(channel_id)
    channel.delete()
    return "ok"


@channel_blueprint.route("/<int:channel_id>/videos")
@login_required
@limiter.shared_limit("1000 per day, 60 per minute", exempt_when=rate_limit_exempt, scope="normal")
@cache.cached(timeout=10, make_cache_key=make_cache_key)
def channel_get_videos(channel_id: int):
    logger.info("Getting videos for channel", extra={"channel_id": channel_id})
    channel = get_channel(channel_id)
    return render_template(
        "channel_edit.html",
        videos=channel.get_videos_sorted_by_uploaded(),
        channel=channel,
        audio_count="{:,}".format(get_stats_videos_with_audio(channel_id)),
        transcription_count="{:,}".format(
            get_stats_videos_with_good_transcription(channel_id)
        ),
    )


@channel_blueprint.route("/<int:channel_id>/fetch_details")
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def channel_fetch_details(channel_id: int):
    logger.info("Fetching details for channel",
                extra={"channel_id": channel_id})
    channel = get_channel(channel_id)
    channel.update()
    return render_template(
        "broadcaster_edit.html",
        broadcaster=channel.broadcaster_id,
        channels=BroadcasterService.get_channels(
            broadcaster_id=channel.broadcaster_id),
        platforms=get_platforms(),
        video_types=VideoType,
    )


@channel_blueprint.route("/<int:channel_id>/fetch_videos")
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def channel_fetch_videos(channel_id: int):
    logger.info("Fetching videos for channel",
                extra={"channel_id": channel_id})
    channel = get_channel(channel_id)
    channel.fetch_latest_videos()
    return redirect(request.referrer)


@channel_blueprint.route("/<int:channel_id>/fetch_videos_all")
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def channel_fetch_videos_all(channel_id: int):
    logger.info("Fetching all videos for channel",
                extra={"channel_id": channel_id})
    channel = get_channel(channel_id)
    channel.fetch_videos_all()
    return redirect(request.referrer)


@channel_blueprint.route("/<int:channel_id>/settings/update", methods=["POST"])
@login_required
@require_permission(check_banned=True)
def channel_settings_update(channel_id: int):
    # Check if user has permission to modify this channel
    channel = db.session.query(Channels).filter_by(id=channel_id).first()
    if not channel:
        if request.headers.get('HX-Request'):
            return '<div class="alert alert-danger">Channel not found</div>', 404
        return "Channel not found", 404

    broadcaster_id = channel.broadcaster_id
    if not (current_user.has_broadcaster_id(broadcaster_id) or current_user.has_permission([PermissionType.Admin])):
        if request.headers.get('HX-Request'):
            return '<div class="alert alert-danger">You do not have permission to modify this channel</div>', 403
        return "You do not have permission to modify this channel", 403

    # Get or create channel settings
    settings = db.session.query(ChannelSettings).filter_by(
        channel_id=channel_id).first()
    if not settings:
        settings = ChannelSettings(channel_id=channel_id)
        db.session.add(settings)

    # Update settings
    content_queue_enabled = 'content_queue_enabled' in request.form
    chat_collection_enabled = 'chat_collection_enabled' in request.form

    logger.info("Updating channel settings, content queue enabled: %s, chat collection enabled: %s",
                content_queue_enabled, chat_collection_enabled, extra={"channel_id": channel_id, "user_id": current_user.id})
    # If content queue is enabled, chat collection must also be enabled
    if content_queue_enabled:
        chat_collection_enabled = True

    settings.content_queue_enabled = content_queue_enabled
    settings.chat_collection_enabled = chat_collection_enabled

    db.session.commit()

    # Check if this is an HTMX request
    if request.headers.get('HX-Request'):
        # Return success message for HTMX
        return f'<div class="alert alert-success">Settings updated for {channel.name}</div>'
    else:
        flash('Channel settings updated successfully')
        return redirect(request.referrer)
