from app.logger import logger
from flask import (
    send_from_directory,
    render_template,
    flash,
    redirect,
    request,
    send_file,
    url_for,
    abort,
    make_response,
    session,
    jsonify,
)
from flask_login import current_user, login_required, logout_user # type: ignore
from app.permissions import require_api_key, require_permission
from datetime import datetime, timedelta
from io import BytesIO
import mimetypes
from app import app, limiter, rate_limit_exempt, socketio
from app.retrievers import (
    get_users,
    get_broadcaster,
    get_broadcasters,
    get_transcription,
    get_user_by_id,
    get_stats_videos,
    get_stats_segments,
    get_video,
    get_platforms,
    get_broadcaster_channels,
    get_channel,
    get_stats_videos_with_audio,
    get_stats_videos_with_good_transcription,
    get_stats_transcriptions,
    get_stats_high_quality_transcriptions,
    get_total_video_duration,
    get_bots,
    get_content_queue,
    get_moderated_channels,
    get_broadcaster_by_external_id,
    get_broadcaster,
)
from app.twitch_api import get_twitch_user
import random
from flask import redirect, url_for, flash, request
from sqlalchemy import select

from app.models.db import (
    Broadcaster,
    Platforms,
    VideoType,
    Channels,
    ChannelSettings,
    PermissionType,
    ContentQueue,
    db,
    BroadcasterSettings,
    ChannelModerator,
    ContentQueueSubmission,
    ContentQueue,
    Content,
    ExternalUser,
    ContentQueueSubmissionSource,
    AccountSource,
    ChatLog,
)

from app.search import search_v2
from app.utils import get_valid_date
import asyncio


def check_banned():
    if current_user.is_anonymous == False and current_user.banned == True:
        return True
    return False



@app.route("/")
@limiter.shared_limit("1000 per day, 60 per minute", exempt_when=rate_limit_exempt, scope="normal")
def index():
    if check_banned():
        return render_template("banned.html", user=current_user)
    broadcasters = get_broadcasters()
    logger.info("Loaded frontpage")
    return render_template("search.html", broadcasters=broadcasters)


@app.route("/login")
def login():
    return render_template("unauthorized.html")

@app.route("/admin")
@limiter.shared_limit("10000 per hour", exempt_when=rate_limit_exempt, scope="images")
def access_denied():
    logger.warning("Access denied", extra={"user_id": current_user.id if not current_user.is_anonymous else None})
    return send_from_directory("static", "401.jpg")

@app.route("/logout")
def logout():
    logout_user()
    flash("You have logged out")
    return render_template("unauthorized.html")

@app.route("/users")
@require_permission(permissions=PermissionType.Admin)
def users():
    users = get_users()
    logger.info("Loaded users.html", extra={"user_id": current_user.id})
    return render_template(
        "users.html", users=users, permission_types=PermissionType
    )

@app.route("/management")
@login_required
@require_permission()
def management():
    logger.info("Loaded management.html")
    moderated_channels = get_moderated_channels(current_user.id)
    bots = None
    if current_user.has_permission(PermissionType.Admin):
        bots = get_bots()
        broadcasters = get_broadcasters()

    elif moderated_channels is not None or current_user.is_broadcaster():
        # Convert moderated channels to a list of broadcasters
        broadcaster_ids = [channel.channel.broadcaster_id for channel in moderated_channels]
        if current_user.is_broadcaster():
            broadcaster_ids.append(current_user.get_broadcaster().id)
        broadcasters = db.session.query(Broadcaster).filter(Broadcaster.id.in_(broadcaster_ids)).all()
    
    if moderated_channels is None and not (current_user.has_permission(PermissionType.Admin) or current_user.is_broadcaster()):
        return "You do not have access", 403
    
    broadcaster_id = request.args.get('broadcaster_id', type=int)
    if broadcaster_id is None and current_user.is_broadcaster():
        broadcaster_id = current_user.get_broadcaster().id
    
    logger.info(f"User is accessing management page", extra={"broadcaster_id": broadcaster_id})
    return render_template(
        "management.html", bots=bots, broadcasters=broadcasters, selected_broadcaster_id=broadcaster_id
    )

@app.route("/management/items")
@login_required
def management_items():
    logger.info("Loading management items with htmx")
    if check_banned():
        return render_template("banned.html", user=current_user)
    
    try:
        # Get filter parameters from request
        broadcaster_id = request.args.get('broadcaster_id', type=int)
        sort_by = request.args.get('sort_by', 'newest')
        
        # Handle checkbox values - checkboxes only send values when checked
        show_watched_param = request.args.get('show_watched')
        show_skipped_param = request.args.get('show_skipped')
        
        # Convert to boolean - 'false' string should be treated as False
        show_watched = show_watched_param != 'false' if show_watched_param is not None else False
        show_skipped = show_skipped_param != 'false' if show_skipped_param is not None else False
        
        # Debug log the received parameters
        logger.debug(f"Filter params: broadcaster_id={broadcaster_id}, sort_by={sort_by}, show_watched={show_watched}, show_skipped={show_skipped}")
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
        if broadcaster.last_active() is None or broadcaster.last_active() < datetime.now() - timedelta(minutes=10):
            queue_items = [item for item in queue_items if item.content.url != "https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
        
        # Apply sorting
        if sort_by == 'oldest':
            # Sort by oldest first (based on first submission date)
            queue_items = sorted(queue_items, key=lambda x: min(s.submitted_at for s in x.submissions) if x.submissions else datetime.now())
        elif sort_by == 'most_submitted':
            # Sort by number of submissions (most first)
            queue_items = sorted(queue_items, key=lambda x: len(x.submissions), reverse=True)
        else:  # 'newest' is default
            # Sort by newest first (based on first submission date)
            queue_items = sorted(queue_items, key=lambda x: min(s.submitted_at for s in x.submissions) if x.submissions else datetime.now(), reverse=True)
        
        logger.info("Successfully loaded management items", extra={
            "broadcaster_id": broadcaster_id, 
            "queue_items": len(queue_items),
            "filters": {"show_watched": show_watched, "show_skipped": show_skipped, "sort_by": sort_by}
        })
        
        return render_template(
            "management_items.html",
            queue_items=queue_items,
            selected_broadcaster_id=broadcaster_id,
            now=datetime.now(),
        )
    except Exception as e:
        logger.error("Error loading management items: %s", e)
        return "Error loading management items", 500

@app.route("/user/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@require_permission(permissions=PermissionType.Admin)
def user_edit(user_id: int):
    user = get_user_by_id(user_id)
    if request.method == "GET":
        logger.info("Loaded users.html")
        broadcasters = get_broadcasters()
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
        return access_denied()
    return "Something went wrong", 503


@app.route("/permissions/<int:user_id>/<permission_name>")
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


@app.route("/stats")
@limiter.limit("100 per day, 5 per minute", exempt_when=rate_limit_exempt)
def stats():
    logger.info("Loaded stats.html")
    return render_template(
        "stats.html",
        video_count="{:,}".format(get_stats_videos()),
        video_duration="{:,}".format(get_total_video_duration()),
        segment_count="{:,}".format(get_stats_segments()),
        transcriptions_count="{:,}".format(get_stats_transcriptions()),
        transcriptions_hq_count="{:,}".format(get_stats_high_quality_transcriptions()),
    )


@app.route("/search")
@limiter.shared_limit("1000 per day, 60 per minute", exempt_when=rate_limit_exempt, scope="normal")
def search_page():
    if check_banned():
        return render_template("banned.html", user=current_user)
    broadcasters = get_broadcasters()
    logger.info(f"Loaded search.html")
    return render_template("search.html", broadcasters=broadcasters)


@app.route("/search", methods=["POST"])
@limiter.shared_limit("100 per day, 5 per minute", exempt_when=rate_limit_exempt, scope="query")
def search_word():
    if check_banned():
        return render_template("banned.html", user=current_user)
    logger.info("User searching something..")
    search_term = request.form["search"]
    broadcaster_id = int(request.form["broadcaster"])
    session["last_selected_broadcaster"] = broadcaster_id
    start_date = get_valid_date(request.form["start_date"])
    end_date = get_valid_date(request.form["end_date"])
    channel_type = request.form["channel_type"]
    broadcaster = get_broadcaster(broadcaster_id)
    channels = [
        channel
        for channel in broadcaster.channels
        if channel.platform.name.lower() == channel_type or channel_type == "all"
    ]
    logger.info("channels: %s", len(channels))
    video_result = search_v2(search_term, channels, start_date, end_date)
    return render_template(
        "result.html",
        search_word=search_term,
        broadcaster=broadcaster,
        video_result=video_result,
    )


@app.route("/broadcasters")
@login_required
@require_permission()
def broadcasters():
    broadcasters = get_broadcasters()
    logger.info("Loaded broadcasters.html")
    return render_template("broadcasters.html", broadcasters=broadcasters)


@app.route("/thumbnails/<int:video_id>")
@limiter.shared_limit("10000 per hour", exempt_when=rate_limit_exempt, scope="images")
def serve_thumbnails(video_id: int):
    try:
        video = get_video(video_id)
        if video.thumbnail is not None:
            content = video.thumbnail.file.read()
            response = make_response(
                send_file(
                    BytesIO(content),
                    mimetype="image/jpeg",
                    download_name=f"{video.id}.jpg",
                )
            )
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return response
    except:
        abort(404)
    abort(500)


@app.route("/video/<int:video_id>/download_audio")
@require_api_key
def serve_audio(video_id: int):
    try:
        video = get_video(video_id)
        if not video or not video.audio:
            abort(404, description="Audio not found")

        # Detect MIME type from the file or store it explicitly
        filename = video.audio.file.filename  # assuming you store this
        mimetype, _ = mimetypes.guess_type(filename)
        mimetype = mimetype or "application/octet-stream"
        content = video.audio.file.read()

        return send_file(
            BytesIO(content),
            mimetype=mimetype,
            as_attachment=True,
            download_name=filename,
        )

    except Exception as e:
        # Log the error to aid debugging
        logger.error(f"Failed to serve audio for video {video_id}: {e}")
        abort(500, description="Internal Server Error")



@app.route("/broadcaster/delete/<int:broadcaster_id>", methods=["GET"])
@login_required
@require_permission(require_broadcaster=True, broadcaster_id_param="broadcaster_id", permissions=PermissionType.Admin)
def broadcaster_delete(broadcaster_id: int):
    logger.warning("Attempting to delete broadcaster %s", broadcaster_id)
    broadcaster = get_broadcaster(broadcaster_id)
    logger.info("Deleting broadcaster %s", broadcaster_id)
    broadcaster.delete()
    return redirect(url_for("broadcasters"))


@app.route("/broadcaster/create", methods=["POST", "GET"])
@login_required
@require_permission()
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
        
            logger.info("Creating new broadcaster: %s for twitch channel: %s", name, twitch_channel)
            if not willbehave:
                flash("You must agree to the terms", "danger")
                logger.warning("Denied adding broadcaster %s - user did not agree to terms", name)
                return render_template("broadcaster_add.html", form=request.form)
            
            if not twitch_channel:
                flash("You must select a Twitch channel", "danger")
                logger.warning("Denied adding broadcaster %s - no twitch channel selected", name)
                return render_template("broadcaster_add.html", form=request.form)
            
            existing_broadcasters = get_broadcasters()
            for broadcaster in existing_broadcasters:
                if broadcaster.name.lower() == name.lower():
                    flash("This broadcaster already exists", "error")
                    logger.warning("Adding broadcaster %s failed - broadcaster already exists", name)
                    return render_template(
                        "broadcaster_add.html",
                        form=request.form
                    )
                    
            # Create the new broadcaster
            new_broadcaster = Broadcaster(name=name, hidden=hidden)
            db.session.add(new_broadcaster)
            db.session.flush()
            
            # Get the platform ID for Twitch
            twitch_platform = db.session.query(Platforms).filter_by(name="Twitch").one()
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
                    linked_discord_channel_id=int(discord_channel_id) if discord_channel_id else None
                )
                db.session.add(broadcaster_settings)
                logger.info("Added initial broadcaster settings - Discord channel ID: %s", discord_channel_id)
            
            if channel_id != current_user.external_account_id:
                db.session.add(
                    ChannelModerator(
                        channel_id=new_broadcaster.id,
                        user_id=current_user.id,
                    )
                )
            db.session.commit()

            intro_clip = db.session.query(Content).filter_by(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ").one_or_none()
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
                    logger.debug("Added intro clip to content queue, tomfoolery", extra={"broadcaster_id": new_broadcaster.id, "queue_item_id": queue_item.id})
                    
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
            logger.info("Broadcaster %s was successfully created", name, extra={"broadcaster_id": new_broadcaster.id})
            return redirect(url_for("broadcaster_edit", id=new_broadcaster.id))
        except Exception as e:
            flash(f"Failed to create broadcaster", "danger")
            logger.error("Failed to create broadcaster %s: %s", name, e)
            return redirect(url_for("broadcaster_add"))


@app.route("/broadcaster/edit/<int:id>", methods=["GET"])
@login_required
@require_permission()
def broadcaster_edit(id: int):
    broadcaster = get_broadcaster(id)
    logger.info("Loaded broadcaster_edit.html", extra={"broadcaster_id": broadcaster.id})
    return render_template(
        "broadcaster_edit.html",
        broadcaster=broadcaster,
        channels=broadcaster.channels,
        platforms=get_platforms(),
        video_types=VideoType,
    )


@app.route("/channel/create", methods=["POST"])
@login_required
#TODO: expand permission check
@require_permission()
def channel_create():
    name = request.form["name"]
    broadcaster_id = int(request.form["broadcaster_id"])
    platform_id = int(request.form["platform_id"])
    platform_ref = request.form["platform_ref"]
    channel_type = request.form["channel_type"]
    channel_id = request.form.get("channel_id", None)
    logger.info("Creating new channel: %s for broadcaster: %s", name, broadcaster_id, extra={"broadcaster_id": broadcaster_id})
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
    logger.info("Channel %s was successfully created", name, extra={"channel_id": new_channel.id, "broadcaster_id": broadcaster_id})
    return render_template(
        "broadcaster_edit.html",
        broadcaster=get_broadcaster(broadcaster_id),
        channels=get_broadcaster_channels(broadcaster_id=broadcaster_id),
        platforms=get_platforms(),
        video_types=VideoType,
    )


@app.route("/channel/<int:channel_id>/link", methods=["POST"])
@login_required
@require_permission(permissions=PermissionType.Admin)
def channel_link(channel_id: int):
    try:
        link_channel_id = int(request.form["link_channel_id"])
    except:
        link_channel_id = None
    logger.info("Linking channel to %s", link_channel_id, extra={"channel_id": channel_id})
    _ = get_channel(channel_id).link_to_channel(link_channel_id)
    return redirect(request.referrer)


@app.route("/channel/<int:channel_id>/look_for_linked")
@login_required
@require_permission(permissions=PermissionType.Admin)
def channel_look_for_linked(channel_id: int):
    channel = get_channel(channel_id)
    logger.info("Looking for linked videos for channel", extra={"channel_id": channel_id})
    # channel.look_for_linked_videos()
    channel.update_thumbnail()
    return redirect(request.referrer)


@app.route("/channel/<int:channel_id>/delete")
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def channel_delete(channel_id: int):
    logger.warning("Deleting channel", extra={"channel_id": channel_id})
    channel = get_channel(channel_id)
    channel.delete()
    return "ok"


@app.route("/channel/<int:channel_id>/videos")
@login_required
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


@app.route("/channel/<int:channel_id>/fetch_details")
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def channel_fetch_details(channel_id: int):
    logger.info("Fetching details for channel", extra={"channel_id": channel_id})
    channel = get_channel(channel_id)
    channel.update()
    return render_template(
        "broadcaster_edit.html",
        broadcaster=channel.broadcaster_id,
        channels=get_broadcaster_channels(broadcaster_id=channel.broadcaster_id),
        platforms=get_platforms(),
        video_types=VideoType,
    )


@app.route("/channel/<int:channel_id>/fetch_videos")
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def channel_fetch_videos(channel_id: int):
    logger.info("Fetching videos for channel", extra={"channel_id": channel_id})
    channel = get_channel(channel_id)
    channel.fetch_latest_videos()
    return redirect(request.referrer)

@app.route("/channel/<int:channel_id>/fetch_videos_all")
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def channel_fetch_videos_all(channel_id: int):
    logger.info("Fetching all videos for channel", extra={"channel_id": channel_id})
    channel = get_channel(channel_id)
    channel.fetch_videos_all()
    return redirect(request.referrer)

@app.route("/video/<int:video_id>/fecth_details")
@login_required
def video_fetch_details(video_id: int):
    logger.info("Fetching details for video", extra={"video_id": video_id})
    video = get_video(video_id)
    video.fetch_details()
    return redirect(request.referrer)


@app.route("/video/<int:video_id>/fetch_transcriptions")
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def video_fetch_transcriptions(video_id: int):
    logger.info("Fetching transcriptions for video", extra={"video_id": video_id})
    video = get_video(video_id)
    video.download_transcription(force=True)
    return redirect(request.referrer)


@app.route("/video/<int:video_id>/archive")
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def video_archive(video_id: int):
    logger.info("Archiving video", extra={"video_id": video_id})
    video = get_video(video_id)
    video.archive()
    return redirect(request.referrer)

@app.route("/video/<int:video_id>/delete")
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def video_delete(video_id: int):
    if current_user.is_anonymous == False and current_user.has_permission(PermissionType.Admin):
        logger.warning("Deleting video", extra={"video_id": video_id})
        video = get_video(video_id)
        channel_id = video.channel_id
        video.delete()
        return redirect(url_for("channel_get_videos", channel_id=channel_id))
    else:
        return "You do not have access", 403

@app.route("/video/<int:video_id>/edit")
@login_required
@limiter.shared_limit("1000 per day, 60 per minute", exempt_when=rate_limit_exempt, scope="normal")
def video_edit(video_id: int):
    video = get_video(video_id)
    return render_template(
        "video_edit.html",
        transcriptions=video.transcriptions,
        video=video,
    )

@app.route("/video/<int:video_id>/chatlogs")
@login_required
@limiter.shared_limit("1000 per day, 60 per minute", exempt_when=rate_limit_exempt, scope="normal")
def video_chatlogs(video_id: int):
    video = get_video(video_id)
    
    # Get chat messages from the channel during the video timeframe
    start_time = video.uploaded
    end_time = video.uploaded + timedelta(seconds=video.duration)
    
    chat_logs = db.session.query(ChatLog).filter(
        ChatLog.channel_id == video.channel_id,
        ChatLog.timestamp >= start_time,
        ChatLog.timestamp <= end_time
    ).order_by(ChatLog.timestamp).all()
    
    return render_template(
        "video_chatlogs.html",
        chat_logs=chat_logs,
        video=video
    )


@app.route("/video/<int:video_id>/parse_transcriptions")
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def video_parse_transcriptions(video_id: int):
    logger.info("Requesting transcriptions to be parsed", extra={"video_id": video_id})
    video = get_video(video_id)
    video.process_transcriptions(force=True)
    return redirect(request.referrer)

@app.route("/transcription/<int:transcription_id>/download")
@login_required
@require_permission()
def download_transcription(transcription_id: int):
    transcription = get_transcription(transcription_id)
    content = transcription.file.file.read()
    return send_file(
        BytesIO(content),
        mimetype="text/plain",
        download_name=f"{transcription.id}.{transcription.file_extention}",
    )

@app.route("/transcription/<int:transcription_id>/download_srt")
@login_required
@require_permission()
def download_transcription_srt(transcription_id: int):
    transcription = get_transcription(transcription_id)
    srt_content = transcription.to_srt()
    return send_file(
        BytesIO(srt_content.encode('utf-8')),
        mimetype="text/plain",
        download_name=f"{transcription.id}.srt",
    )

@app.route("/transcription/<int:transcription_id>/download_json")
@login_required
@require_permission()
def download_transcription_json(transcription_id: int):
    transcription = get_transcription(transcription_id)
    json_content = transcription.to_json()
    return send_file(
        BytesIO(json_content.encode('utf-8')),
        mimetype="application/json",
        download_name=f"{transcription.id}.json",
    )

@app.route("/clip_queue")
@login_required
@require_permission()
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
            "clip_queue.html",
            queue_items=queue_items,
            broadcaster=broadcaster,
            motd=random.choice(messages),
            now=datetime.now(),
        )
    except Exception as e:
        logger.error("Error loading clip queue %s", e)
        return "You do not have access", 403


@app.route("/clip_queue/mark_watched/<int:item_id>", methods=["POST"])
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


@app.route("/clip_queue/item/<int:item_id>/skip", methods=["POST"])
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


@app.route("/clip_queue/items")
@login_required
@require_permission()
def get_queue_items():
    logger.info("Loading clip queue with htmx")
    try:
        broadcaster = get_broadcaster_by_external_id(current_user.external_account_id) 
        queue_enabled = False
        for channel in broadcaster.channels:
            if channel.platform.name.lower() == "twitch" and channel.settings.content_queue_enabled:
                queue_enabled = True
                break
        if broadcaster is not None and queue_enabled:
            queue_items = get_content_queue(broadcaster.id)
            if broadcaster.last_active() is None or broadcaster.last_active() < datetime.now() - timedelta(minutes=10):
                queue_items = [item for item in queue_items if item.content.url != "https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
            if len(queue_items) == 0:
                return "No more clips :("
            logger.info("Successfully loaded clip queue", extra={"broadcaster_id": broadcaster.id, "queue_items": len(queue_items), "user_id": current_user.id})
            return render_template(
                "clip_queue_items.html",
                queue_items=queue_items,
                broadcaster=broadcaster,
                now=datetime.now(),
            )
        elif broadcaster is not None and not queue_enabled:
            return "You have disabled the queue, visit <a href='/broadcaster/edit/" + str(broadcaster.id) + "'>broadcaster settings</a> to enable it"
        else:
            return "You do not have access, no broadcaster_id found on you", 403
    except Exception as e:
        logger.error("Error loading clip queue %s", e, extra={"user_id": current_user.id})
        return "Error loading clip queue", 500


@app.route("/broadcaster/<int:broadcaster_id>/create_clip")
@login_required
def broadcaster_create_clip(broadcaster_id: int):
    # Check if user has permission to modify this broadcaster
    logger.info("Attempting to create clip for broadcaster", extra={"broadcaster_id": broadcaster_id})
    if current_user.is_anonymous or not (current_user.broadcaster_id == broadcaster_id or current_user.has_permission(["admin"])):
        logger.error("User does not have permission to create clip for broadcaster", extra={"broadcaster_id": broadcaster_id})
        return "You do not have permission to modify this broadcaster", 403
    
    # Add clip creation task to Redis queue
    from app import redis_task_queue
    task_id = redis_task_queue.enqueue_clip_creation(str(broadcaster_id))
    
    if task_id:
        flash("Clip creation task queued successfully")
        logger.info("Clip creation task %s queued for broadcaster", task_id, extra={"broadcaster_id": broadcaster_id, "user_id": current_user.id})
    else:
        flash("Failed to queue clip creation task", "error")
        logger.error("Failed to queue clip creation task for broadcaster", extra={"broadcaster_id": broadcaster_id, "user_id": current_user.id})
    
    return redirect(request.referrer)


@app.route("/purge_transcription/<int:transcription_id>")
@require_permission(permissions=PermissionType.Admin)
def purge_transcription(transcription_id: int):
    logger.info("Purging transcription", extra={"transcription_id": transcription_id, "user_id": current_user.id})
    transcription = get_transcription(transcription_id)
    transcription.reset()
    return redirect(request.referrer)

@app.route("/transcription/<int:transcription_id>/delete")
@require_permission(check_banned=True)
def delete_transcription(transcription_id: int):
    transcription = get_transcription(transcription_id)
    broadcaster_id = transcription.video.channel.broadcaster_id
    
    # Custom permission check since we need to check multiple conditions
    if current_user.has_permission([PermissionType.Admin, PermissionType.Moderator]) or current_user.has_broadcaster_id(broadcaster_id):
        logger.info("Deleting transcription", extra={"transcription_id": transcription_id, "video_id": transcription.video_id, "user_id": current_user.id})
        transcription.delete()
        db.session.commit()
        return redirect(request.referrer)
    else:
        logger.error("User does not have permission to delete transcription", extra={"transcription_id": transcription_id, "video_id": transcription.video_id, "user_id": current_user.id})
        return access_denied()

@app.route("/broadcaster/<int:broadcaster_id>/settings/update", methods=["POST"])
@require_permission(permissions=[PermissionType.Admin], require_broadcaster=True, broadcaster_id_param="broadcaster_id", check_banned=True)
def broadcaster_settings_update(broadcaster_id: int):
    settings = db.session.query(BroadcasterSettings).filter_by(broadcaster_id=broadcaster_id).first()
    if not settings:
        settings = BroadcasterSettings(broadcaster_id=broadcaster_id)
        db.session.add(settings)
    
    discord_channel_id = request.form.get('discord_channel_id')
    settings.linked_discord_channel_id = int(discord_channel_id) if discord_channel_id else None
    
    logger.info("Updating broadcaster settings, linked discord channel id: %s", discord_channel_id, extra={"broadcaster_id": broadcaster_id, "user_id": current_user.id})
    
    # Update broadcaster hidden status (admin only)
    if current_user.has_permission([PermissionType.Admin]) and request.form.get('hidden'):
        broadcaster = db.session.query(Broadcaster).filter_by(id=broadcaster_id).first()
        if broadcaster:
            broadcaster.hidden = 'hidden' in request.form
            logger.info("Updating broadcaster hidden status, hidden: %s", 'hidden' in request.form, extra={"broadcaster_id": broadcaster_id, "user_id": current_user.id})
    
    db.session.commit()
    flash('Broadcaster settings updated successfully')
    return redirect(request.referrer)


@app.route("/channel/<int:channel_id>/settings/update", methods=["POST"])
@require_permission(check_banned=True)
def channel_settings_update(channel_id: int):
    # Check if user has permission to modify this channel
    channel = db.session.query(Channels).filter_by(id=channel_id).first()
    if not channel:
        return "Channel not found", 404
    
    broadcaster_id = channel.broadcaster_id
    if not (current_user.has_broadcaster_id(broadcaster_id) or current_user.has_permission([PermissionType.Admin])):
        return access_denied()
    
    # Get or create channel settings
    settings = db.session.query(ChannelSettings).filter_by(channel_id=channel_id).first()
    if not settings:
        settings = ChannelSettings(channel_id=channel_id)
        db.session.add(settings)
    
    # Update settings
    content_queue_enabled = 'content_queue_enabled' in request.form
    chat_collection_enabled = 'chat_collection_enabled' in request.form
    
    logger.info("Updating channel settings, content queue enabled: %s, chat collection enabled: %s", content_queue_enabled, chat_collection_enabled, extra={"channel_id": channel_id, "user_id": current_user.id})
    # If content queue is enabled, chat collection must also be enabled
    if content_queue_enabled:
        chat_collection_enabled = True
        
    settings.content_queue_enabled = content_queue_enabled
    settings.chat_collection_enabled = chat_collection_enabled
    
    db.session.commit()
    flash('Channel settings updated successfully')
    return redirect(request.referrer)


@app.route("/api/lookup_twitch_id")
@login_required
def lookup_twitch_id():
    """API endpoint to look up a Twitch user ID by username"""
    if check_banned():
        return jsonify({"success": False, "error": "You are banned"})
    if current_user.is_anonymous:
        return jsonify({"success": False, "error": "You must be logged in to use this endpoint"})
    username = request.args.get("username")
    if not username:
        return jsonify({"success": False, "error": "No username provided"})
    
    try:
        # Use the existing Twitch API function to look up the user
        user = asyncio.run(get_twitch_user(username))
        if user:
            return jsonify({"success": True, "user_id": user.id, "display_name": user.display_name})
        else:
            return jsonify({"success": False, "error": "User not found"})
    except Exception as e:
        logger.error(f"Error looking up Twitch user: {e}")
        return jsonify({"success": False, "error": str(e)})
