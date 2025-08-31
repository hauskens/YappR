from flask import Blueprint, render_template, redirect, request, flash, jsonify
from app.logger import logger
from flask_login import current_user, login_required  # type: ignore
from app.permissions import require_permission
from app.models import db
from app.models import Channels, VideoType, PermissionType, ChannelSettings, PlatformType, ChannelRole, ChannelCreate
from app.models.channel import ChannelEvent
from app.services import BroadcasterService, ChannelService
from app.services.video_date_estimation import VideoDateEstimationService
from app.rate_limit import limiter, rate_limit_exempt

channel_blueprint = Blueprint('channel', __name__, url_prefix='/channel',
                              template_folder='templates', static_folder='static')


@channel_blueprint.route("/create", methods=["POST"])
@login_required
@require_permission(check_broadcaster=True, check_moderator=True, permissions=PermissionType.Moderator)
def channel_create():
    name = request.form["name"]
    broadcaster_id = int(request.form["broadcaster_id"])
    platform_name = request.form["platform_name"]
    platform_ref = request.form["platform_ref"]
    channel_type = request.form["channel_type"]
    channel_id = request.form.get("channel_id", None)
    logger.info("Creating new channel: %s for broadcaster: %s", name,
                broadcaster_id, extra={"broadcaster_id": broadcaster_id})
    new_channel = ChannelService.create(ChannelCreate(
        name=name,
        broadcaster_id=broadcaster_id,
        platform_name=platform_name.lower(),
        platform_ref=platform_ref,
        main_video_type=channel_type.lower(),
        platform_channel_id=channel_id,
    ))
    logger.info("Channel %s was successfully created", name, extra={
                "channel_id": new_channel.id, "broadcaster_id": broadcaster_id})
    return redirect(request.referrer)


@channel_blueprint.route("/<int:channel_id>/link", methods=["POST"])
@login_required
@require_permission(permissions=PermissionType.Admin)
def channel_link(channel_id: int):
    """Link channel to another channel (set source_channel_id)"""
    channel = ChannelService.get_by_id(channel_id)
    if not channel:
        flash('Channel not found', 'error')
        return redirect(request.referrer)

    link_channel_id = request.form.get('link_channel_id')
    
    try:
        if link_channel_id == 'None' or not link_channel_id:
            # Unlink channel
            ChannelService.link_to_channel(channel, None)
        else:
            # Link to target channel
            target_channel_id = int(link_channel_id)
            ChannelService.link_to_channel(channel, target_channel_id)

    except ValueError as e:
        flash(f'Error linking channel: {str(e)}', 'error')
        logger.error(f"Error linking channel {channel_id}: {e}",
                    extra={"channel_id": channel_id, "user_id": current_user.id})
    except Exception as e:
        flash(f'Unexpected error: {str(e)}', 'error')
        logger.error(f"Unexpected error linking channel {channel_id}: {e}",
                    extra={"channel_id": channel_id, "user_id": current_user.id})

    # Check if this is a fetch request (AJAX) - fetch API typically doesn't set referrer policy the same way
    # or we can check if it came from our modal (no referrer header in some cases)
    is_fetch_request = (
        request.headers.get('X-Requested-With') == 'fetch' or
        'application/json' in request.headers.get('Accept', '') or
        not request.referrer  # Fetch from modal might not have referrer
    )
    
    if is_fetch_request:
        return jsonify({"success": True})
    else:
        return redirect(request.referrer)

@channel_blueprint.route("/<int:channel_id>/look_for_linked")
@login_required
@require_permission(permissions=PermissionType.Admin)
def channel_look_for_linked(channel_id: int):
    channel = ChannelService.get_by_id(channel_id)
    logger.info("Looking for linked videos for channel",
                extra={"channel_id": channel_id})
    ChannelService.update_thumbnails(channel)
    return redirect(request.referrer)


@channel_blueprint.route("/<int:channel_id>/delete")
@login_required
@require_permission(permissions=[PermissionType.Admin], check_broadcaster=True)
def channel_delete(channel_id: int):
    logger.warning("Deleting channel", extra={"channel_id": channel_id})
    ChannelService.delete_channel(channel_id)
    return redirect(request.referrer)


@channel_blueprint.route("/<int:channel_id>/videos")
@login_required
@limiter.shared_limit("1000 per day, 60 per minute", exempt_when=rate_limit_exempt, scope="normal")
@require_permission(check_broadcaster=True, check_anyone=True)
def channel_get_videos(channel_id: int):
    logger.info("Getting videos for channel", extra={"channel_id": channel_id})
    channel = ChannelService.get_by_id(channel_id)
    return render_template(
        "channel_edit.html",
        videos=ChannelService.get_videos_by_channel(channel_id),
        channel=channel,
        audio_count="{:,}".format(
            ChannelService.get_stats_videos_with_audio(channel_id)),
        transcription_count="{:,}".format(
            ChannelService.get_stats_videos_with_good_transcription(channel_id)
        ),
    )


@channel_blueprint.route("/<int:channel_id>/fetch_details")
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator], check_broadcaster=True)
def channel_fetch_details(channel_id: int):
    logger.info("Fetching details for channel",
                extra={"channel_id": channel_id})
    channel = ChannelService.get_by_id(channel_id)
    ChannelService.update_channel_details(channel)
    return redirect(request.referrer)


@channel_blueprint.route("/<int:channel_id>/fetch_videos")
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator], check_broadcaster=True)
def channel_fetch_videos(channel_id: int):
    logger.info("Fetching videos for channel",
                extra={"channel_id": channel_id})
    channel = ChannelService.get_by_id(channel_id)
    ChannelService.fetch_latest_videos(channel)
    return redirect(request.referrer)


@channel_blueprint.route("/<int:channel_id>/fetch_videos_all")
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def channel_fetch_videos_all(channel_id: int):
    logger.info("Fetching all videos for channel",
                extra={"channel_id": channel_id})
    channel = ChannelService.get_by_id(channel_id)
    ChannelService.fetch_all_videos(channel)
    return redirect(request.referrer)


@channel_blueprint.route("/<int:channel_id>/settings/update", methods=["POST"])
@login_required
@require_permission(check_broadcaster=True, check_moderator=True, channel_roles=[ChannelRole.Owner, ChannelRole.Mod])
def channel_settings_update(channel_id: int):
    # Check if user has permission to modify this channel
    channel = ChannelService.get_by_id(channel_id)
    if not channel:
        if request.headers.get('HX-Request'):
            return '<div class="alert alert-danger">Channel not found</div>', 404
        return "Channel not found", 404


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

    # Update main video type if provided
    main_video_type = request.form.get('main_video_type')
    if main_video_type:
        try:
            # Convert string name to VideoType enum
            new_video_type = VideoType[main_video_type]
            channel.main_video_type = new_video_type
            logger.info("Updated channel main_video_type to %s", main_video_type, 
                       extra={"channel_id": channel_id, "user_id": current_user.id})
        except KeyError:
            logger.error("Invalid video type: %s", main_video_type, 
                        extra={"channel_id": channel_id, "user_id": current_user.id})

    db.session.commit()

    # Check if this is an HTMX request
    if request.headers.get('HX-Request'):
        # Return success message for HTMX
        return f'<div class="alert alert-success">Settings updated for {channel.name}</div>'
    else:
        return redirect(request.referrer)


@channel_blueprint.route("/<int:channel_id>/link_videos", methods=["POST"])
@login_required
@require_permission(check_broadcaster=True, check_moderator=True, channel_roles=[ChannelRole.Owner, ChannelRole.Mod])
def channel_link_videos(channel_id: int):
    """Run enhanced video linking for all videos in the channel"""
    channel = ChannelService.get_by_id(channel_id)
    if not channel:
        flash('Channel not found', 'error')
        return redirect(request.referrer)

    if not channel.source_channel:
        flash('No source channel configured for linking', 'error')
        return redirect(request.referrer)

    try:
        # Get parameters from form (with defaults)
        margin_sec = int(request.form.get('margin_sec', 2))
        min_duration = int(request.form.get('min_duration', 300))
        date_margin_hours = int(request.form.get('date_margin_hours', 48))

        logger.info(f"Running video linking for channel {channel.name} with parameters: "
                   f"margin_sec={margin_sec}, min_duration={min_duration}, date_margin_hours={date_margin_hours}",
                   extra={"channel_id": channel_id, "user_id": current_user.id})

        # Run the enhanced video linking
        ChannelService.look_for_linked_videos(
            channel=channel, 
            margin_sec=margin_sec,
            min_duration=min_duration,
            date_margin_hours=date_margin_hours
        )

        flash(f'Video linking completed for {channel.name}. Check the logs for details.', 'success')

    except Exception as e:
        logger.error(f"Error running video linking for channel {channel_id}: {e}", 
                    extra={"channel_id": channel_id, "user_id": current_user.id})
        flash(f'Error running video linking: {str(e)}', 'error')

    return redirect(request.referrer)


@channel_blueprint.route("/<int:channel_id>/bulk_auto_link", methods=["POST"])
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def channel_bulk_auto_link(channel_id: int):
    """Bulk auto-link videos where both Duration and Date matches are found"""
    channel = ChannelService.get_by_id(channel_id)
    if not channel:
        flash('Channel not found', 'error')
        return redirect(request.referrer)

    if not channel.source_channel:
        flash('No source channel configured for linking', 'error')
        return redirect(request.referrer)

    try:
        # Get parameters from form (with defaults)
        margin_sec = int(request.form.get('margin_sec', 2))
        min_duration = int(request.form.get('min_duration', 300))
        date_margin_hours = int(request.form.get('date_margin_hours', 48))

        logger.info(f"Running bulk auto-link for channel {channel.name} with parameters: "
                   f"margin_sec={margin_sec}, min_duration={min_duration}, date_margin_hours={date_margin_hours}",
                   extra={"channel_id": channel_id, "user_id": current_user.id})

        # Run the bulk auto-link with strict criteria (both duration and date must match)
        linked_count = ChannelService.bulk_auto_link_videos(
            channel=channel, 
            margin_sec=margin_sec,
            min_duration=min_duration,
            date_margin_hours=date_margin_hours
        )

        if linked_count > 0:
            flash(f'Successfully auto-linked {linked_count} videos for {channel.name}.', 'success')
        else:
            flash(f'No videos found that meet both Duration AND Date criteria for auto-linking.', 'info')

    except Exception as e:
        logger.error(f"Error running bulk auto-link for channel {channel_id}: {e}", 
                    extra={"channel_id": channel_id, "user_id": current_user.id})
        flash(f'Error running bulk auto-link: {str(e)}', 'error')

    return redirect(request.referrer)



@channel_blueprint.route("/<int:channel_id>/estimate_upload_times", methods=["POST"])
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator], check_broadcaster=True)
def channel_estimate_upload_times(channel_id: int):
    """Bulk estimate upload times for videos using title dates and live events"""
    channel = ChannelService.get_by_id(channel_id)
    if not channel:
        flash('Channel not found', 'error')
        return redirect(request.referrer)

    try:
        # Get parameters (with defaults)
        date_margin_hours = int(request.form.get('date_margin_hours', 48))
        duration_margin_seconds = int(request.form.get('duration_margin_seconds', 20))
        
        logger.info(f"Running bulk upload time estimation for channel {channel.name} with date margin {date_margin_hours}h and duration margin {duration_margin_seconds}s",
                   extra={"channel_id": channel_id, "user_id": current_user.id})

        # Run the bulk date estimation
        result = VideoDateEstimationService.estimate_upload_times_for_channel(
            channel_id=channel_id,
            date_margin_hours=date_margin_hours,
            duration_margin_seconds=duration_margin_seconds
        )

        updated_count = result['updated_count']
        total_processed = result['total_processed']
        
        return jsonify({
            "success": True,
            "updated_count": updated_count,
            "total_processed": total_processed,
            "message": f"Successfully estimated upload times for {updated_count} out of {total_processed} videos in {channel.name}."
        })

    except Exception as e:
        logger.error(f"Error running bulk upload time estimation for channel {channel_id}: {e}", 
                    extra={"channel_id": channel_id, "user_id": current_user.id})
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
