import logging
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
)
from flask_login import current_user, login_required, logout_user # type: ignore
from .utils import require_api_key
from io import BytesIO
import json
import mimetypes
from . import app, limiter, rate_limit_exempt
import os
from .models.config import config
from .retrievers import (
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
    get_all_twitch_channels,
)

from .models.db import (
    Broadcaster,
    Platforms,
    VideoType,
    Channels,
    ChannelSettings,
    PermissionType,
    Transcription,
    TranscriptionSource,
    ContentQueue,
    Content,
    db,
)

from .models.transcription import TranscriptionResult
from .search import search_v2
from .utils import get_valid_date

logger = logging.getLogger(__name__)


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
    logger.info("Loaded search.html")
    return render_template("search.html", broadcasters=broadcasters)


@app.route("/login")
def login():
    return render_template("unauthorized.html")

@app.route("/admin")
@limiter.shared_limit("10000 per hour", exempt_when=rate_limit_exempt, scope="images")
def access_denied():
    return send_from_directory("static", "401.jpg")

@app.route("/logout")
def logout():
    logout_user()
    flash("You have logged out")
    return render_template("unauthorized.html")

@app.route("/users")
@login_required
def users():
    if check_banned():
        return render_template("banned.html", user=current_user)
    users = get_users()
    logger.info("Loaded users.html")
    if current_user.is_anonymous == False and current_user.has_permission(PermissionType.Admin):
        return render_template(
            "users.html", users=users, permission_types=PermissionType
        )
    else:
        return "You do not have access", 403

@app.route("/management")
@login_required
def management():
    if check_banned():
        return render_template("banned.html", user=current_user)
    logger.info("Loaded management.html")
    if current_user.is_anonymous == False and current_user.has_permission(PermissionType.Admin):
        bots = get_bots()
        return render_template(
            "management.html", bots=bots
        )
    else:
        return "You do not have access", 403

@app.route("/user/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
def user_edit(user_id: int):
    if check_banned():
        return render_template("banned.html", user=current_user)
    if current_user.is_anonymous == False and current_user.has_permission(PermissionType.Admin):
        user = get_user_by_id(user_id)
        if request.method == "GET":
            logger.info("Loaded users.html")
            if current_user.is_anonymous == False and current_user.has_permission(PermissionType.Admin):
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
                    f"User {user.id}, changing broadcaster_id to: '{broadcaster_id}'"
                )
                return redirect(request.referrer)
            except:
                user.broadcaster_id = None
                db.session.commit()
                logger.info(f"User {user.id}, changing broadcaster_id to: None")
                return redirect(request.referrer)

    else:
        return access_denied()
    return "Something went wrong", 503


@app.route("/permissions/<int:user_id>/<permission_name>")
@login_required
def grant_permission(user_id: int, permission_name: str):
    if current_user.is_anonymous == False and current_user.has_permission(PermissionType.Admin):
        logger.info(
            f"User {current_user.id} is granting '{permission_name}' to {user_id}"
        )

        user = get_user_by_id(user_id)
        _ = user.add_permissions(PermissionType[permission_name])
        users = get_users()
        return render_template(
            "users.html", users=users, permission_types=PermissionType
        )
    else:
        return access_denied()


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
    logger.info(f"channels: {len(channels)}")
    video_result = search_v2(search_term, channels, start_date, end_date)
    return render_template(
        "result.html",
        search_word=search_term,
        broadcaster=broadcaster,
        video_result=video_result,
    )


@app.route("/broadcasters")
@login_required
def broadcasters():
    if check_banned():
        return render_template("banned.html", user=current_user)
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


@app.route("/platforms")
@login_required
def platforms():
    platforms = get_platforms()
    logger.info("Loaded platforms.html")
    return render_template("platforms.html", platforms=platforms)


@app.route("/broadcaster/create", methods=["POST"])
@login_required
def broadcaster_create():
    name = request.form["name"]
    existing_broadcasters = get_broadcasters()
    for broadcaster in existing_broadcasters:
        if broadcaster.name.lower() == name.lower():
            flash("This broadcaster already exists", "error")
            return render_template(
                "broadcasters.html",
                form=request.form,
                broadcasters=existing_broadcasters,
            )
    db.session.add(Broadcaster(name=name))
    db.session.commit()
    return redirect(url_for("broadcasters"))


@app.route("/broadcaster/edit/<int:id>", methods=["GET"])
@login_required
def broadcaster_edit(id: int):
    broadcaster = get_broadcaster(id)
    return render_template(
        "broadcaster_edit.html",
        broadcaster=broadcaster,
        channels=broadcaster.channels,
        platforms=get_platforms(),
        video_types=VideoType,
    )


@app.route("/platform/create", methods=["POST"])
@login_required
def platform_create():
    name = request.form["name"]
    url = request.form["url"]
    existing_platforms = get_platforms()
    if existing_platforms is not None:
        for platform in existing_platforms:
            if platform.name.lower() == name.lower():
                flash("This platform already exists", "error")
                return render_template(
                    "platforms.html",
                    form=request.form,
                    broadcasters=existing_platforms,
                )
    abt = Platforms(name=name, url=url)
    db.session.add(abt)
    db.session.commit()
    return redirect(url_for("platforms"))


@app.route("/channel/create", methods=["POST"])
@login_required
def channel_create():
    name = request.form["name"]
    broadcaster_id = int(request.form["broadcaster_id"])
    platform_id = int(request.form["platform_id"])
    platform_ref = request.form["platform_ref"]
    channel_type = request.form["channel_type"]
    db.session.add(
        Channels(
            name=name,
            broadcaster_id=broadcaster_id,
            platform_id=platform_id,
            platform_ref=platform_ref,
            main_video_type=channel_type,
        )
    )
    db.session.commit()
    return render_template(
        "broadcaster_edit.html",
        broadcaster=broadcaster_id,
        channels=get_broadcaster_channels(broadcaster_id=broadcaster_id),
        platforms=get_platforms(),
        video_types=VideoType,
    )


@app.route("/channel/<int:channel_id>/link", methods=["POST"])
@login_required
def channel_link(channel_id: int):
    try:
        link_channel_id = int(request.form["link_channel_id"])
    except:
        link_channel_id = None
    _ = get_channel(channel_id).link_to_channel(link_channel_id)
    return redirect(request.referrer)


@app.route("/channel/<int:channel_id>/look_for_linked")
@login_required
def channel_look_for_linked(channel_id: int):
    channel = get_channel(channel_id)
    # channel.look_for_linked_videos()
    channel.update_thumbnail()
    return redirect(request.referrer)


@app.route("/channel/<int:channel_id>/delete")
@login_required
def channel_delete(channel_id: int):
    channel = get_channel(channel_id)
    channel.delete()
    return "ok"


@app.route("/channel/<int:channel_id>/videos")
@login_required
def channel_get_videos(channel_id: int):
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
def channel_fetch_details(channel_id: int):
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
def channel_fetch_videos(channel_id: int):
    channel = get_channel(channel_id)
    logger.info(f"Fetching videos for {channel.name}")
    channel.fetch_latest_videos()
    return redirect(request.referrer)

@app.route("/channel/<int:channel_id>/fetch_videos_all")
@login_required
def channel_fetch_videos_all(channel_id: int):
    channel = get_channel(channel_id)
    logger.info(f"Fetching videos for {channel.name}")
    channel.fetch_videos_all()
    return redirect(request.referrer)

@app.route("/video/<int:video_id>/fecth_details")
@login_required
def video_fetch_details(video_id: int):
    logger.info(f"Fetching details for {video_id}")
    video = get_video(video_id)
    video.fetch_details()
    return redirect(request.referrer)


@app.route("/video/<int:video_id>/fetch_transcriptions")
@login_required
def video_fetch_transcriptions(video_id: int):
    logger.info(f"Fetching transcriptions for {video_id}")
    video = get_video(video_id)
    video.download_transcription(force=True)
    return redirect(request.referrer)


@app.route("/video/<int:video_id>/archive")
@login_required
def video_archive(video_id: int):
    logger.info(f"Archiving video {video_id}")
    video = get_video(video_id)
    video.archive()
    return redirect(request.referrer)

@app.route("/video/<int:video_id>/delete")
@login_required
def video_delete(video_id: int):
    if current_user.is_anonymous == False and current_user.has_permission(PermissionType.Admin):
        logger.info(f"Deleting video {video_id}")
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


@app.route("/video/<int:video_id>/parse_transcriptions")
@login_required
def video_parse_transcriptions(video_id: int):
    video = get_video(video_id)
    video.process_transcriptions(force=True)
    return redirect(request.referrer)

@app.route("/transcription/<int:transcription_id>/download")
@login_required
def download_transcription(transcription_id: int):
    transcription = get_transcription(transcription_id)
    content = transcription.file.file.read()
    return send_file(
        BytesIO(content),
        mimetype="text/plain",
        download_name=f"{transcription.id}.{transcription.file_extention}",
    )

@app.route("/content_queue")
@limiter.shared_limit("1000 per day, 60 per minute", exempt_when=rate_limit_exempt, scope="normal")
@login_required
def content_queue():
    if check_banned():
        return render_template("banned.html", user=current_user)
    
    # Get channel_id from query parameter if it exists
    channel_id = request.args.get('channel_id', type=int)
    
    # Get content queue items filtered by channel_id if provided
    queue_items = get_content_queue(channel_id)
    
    # Get all Twitch channels for the dropdown
    twitch_channels = get_all_twitch_channels()
    
    return render_template(
        "content_queue.html",
        queue_items=queue_items,
        twitch_channels=twitch_channels,
        selected_channel_id=channel_id
    )


@app.route("/transcription/<int:transcription_id>/purge")
@login_required
def purge_transcription(transcription_id: int):
    if current_user.is_anonymous == False and current_user.has_permission(
        PermissionType.Admin
    ):
        transcription = get_transcription(transcription_id)
        transcription.reset()
        return redirect(request.referrer)
    else:
        return access_denied()

@app.route("/transcription/<int:transcription_id>/delete")
@login_required
def delete_transcription(transcription_id: int):
    transcription = get_transcription(transcription_id)
    transcription.delete()
    db.session.commit()
    return redirect(request.referrer)

@app.route("/channel/<int:channel_id>/settings/update", methods=["POST"])
@login_required
def channel_settings_update(channel_id: int):
    channel = get_channel(channel_id)
    
    # Check if user has permission to modify this channel
    if current_user.is_anonymous or not (current_user.external_account_id == channel.broadcaster_id or current_user.has_permission(["admin"])):
        return "You do not have permission to modify this channel", 403
    
    # Get or create channel settings
    settings = db.session.query(ChannelSettings).filter_by(channel_id=channel_id).first()
    if not settings:
        settings = ChannelSettings(channel_id=channel_id)
        db.session.add(settings)
    
    # Update settings
    settings.content_queue_enabled = 'content_queue_enabled' in request.form
    settings.chat_collection_enabled = 'chat_collection_enabled' in request.form
    
    db.session.commit()
    flash('Channel settings updated successfully')
    return redirect(request.referrer)
