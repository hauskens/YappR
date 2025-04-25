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
    session,
    g,
)
from flask_login import current_user, login_required
from io import BytesIO
import json
from . import app
import os
from .models.config import config
from .retrievers import (
    get_users,
    get_broadcaster,
    get_broadcasters,
    get_transcription,
    get_user_by_id,
    get_stats_words,
    get_stats_videos,
    get_stats_segments,
    add_log,
    get_video,
    get_platforms,
    get_broadcaster_channels,
    get_channel,
    get_transcriptions_by_video,
)

from .models.db import (
    Broadcaster,
    Platforms,
    VideoType,
    Channels,
    PermissionType,
    Transcription,
    TranscriptionSource,
    db,
)

from .models.transcription import TranscriptionResult
from .search import search_v2
from .utils import get_valid_date

logger = logging.getLogger(__name__)


def check_banned():
    if current_user.is_authenticated and current_user.banned == True:
        return True
    return False


@app.route("/")
@login_required
def index():
    if check_banned():
        return render_template("banned.html", user=current_user)
    broadcasters = get_broadcasters()
    logger.info("Loaded search.html")
    return render_template("search.html", broadcasters=broadcasters)


@app.route("/admin")
def access_denied():
    return send_from_directory("static", "401.jpg")


@app.route("/users")
@login_required
def users():
    if check_banned():
        return render_template("banned.html", user=current_user)
    users = get_users()
    logger.info("Loaded users.html")
    if current_user.has_permission(PermissionType.Admin):
        return render_template(
            "users.html", users=users, permission_types=PermissionType
        )
    else:
        return "You do not have access", 403


@app.route("/permissions/<int:user_id>/<permission_name>")
@login_required
def grant_permission(user_id: int, permission_name: str):
    if current_user.has_permission(PermissionType.Admin):
        logger.info(
            f"User {current_user.user_id} is granting '{permission_name}' to {user_id}"
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
@login_required
def stats():
    logger.info("Loaded stats.html")
    return render_template(
        "stats.html",
        video_count="{:,}".format(get_stats_videos()),
        word_count="{:,}".format(get_stats_words()),
        segment_count="{:,}".format(get_stats_segments()),
    )


@app.route("/search")
@login_required
def search_page():
    if check_banned():
        return render_template("banned.html", user=current_user)
    broadcasters = get_broadcasters()
    logger.info(f"Loaded search.html")
    return render_template("search.html", broadcasters=broadcasters)


@app.route("/search", methods=["POST"])
@login_required
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
    add_log(f"Searching for '{search_term}' on {broadcaster.name}")
    segment_result, video_result = search_v2(
        search_term, channels, start_date, end_date
    )
    if len(segment_result) == 0:
        flash(
            "Could not find any videos based on that search, try something else",
            "error",
        )
        return redirect(request.referrer)

    return render_template(
        "result.html",
        search_word=search_term,
        broadcaster=broadcaster,
        video_result=video_result,
        segment_result=segment_result,
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
@login_required
def serve_thumbnails(video_id: int):
    try:
        video = get_video(video_id)
        if video.thumbnail is not None:
            content = video.thumbnail.file.read()
            return send_file(
                BytesIO(content),
                mimetype="image/jpeg",
                download_name=f"{video.id}.jpg",
            )
    except:
        abort(404)
    abort(500)


@app.route("/video/<int:video_id>/download_audio")
def serve_audio(video_id: int):
    try:
        video = get_video(video_id)
        if video.audio is not None:
            content = video.audio.file.read()
            return send_file(
                BytesIO(content),
                mimetype="audio/mpeg",
                download_name=f"{video.id}.webm",
            )
    except:
        abort(404)
    abort(500)


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


@app.route("/channel/<int:channel_id>/delete")
@login_required
def channel_delete(channel_id: int):
    channel = get_channel(channel_id)
    channel.delete()
    return "ok"


@app.route("/channel/<int:channel_id>/get_videos")
@login_required
def channel_get_videos(channel_id: int):
    channel = get_channel(channel_id)
    return render_template("channel_edit.html", videos=channel.videos, channel=channel)


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


# temp disabled, cant have this accidentaly run as it eats up api rate limit
# @app.route("/channel/<int:channel_id>/fetch_audio")
# @login_required
# def channel_fetch_audio(channel_id: int):
#     channel = get_channel(channel_id)
#     logger.info(f"Fetching all audio for {channel.name}")
#     for video in channel.videos:
#         _ = task_audio.delay(video.id)
#     return redirect(url_for("channel_get_videos", channel_id=channel.id))


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
    video.save_transcription(force=True)
    return redirect(request.referrer)


@app.route("/video/<int:video_id>/edit")
@login_required
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
    tran = get_transcriptions_by_video(video_id)
    if tran is not None:
        for t in tran:
            t.process_transcription()
    return redirect(request.referrer)


# @app.route("/video/<int:video_id>/download_clip", methods=["POST"])
# @login_required
# def download_video_clip(video_id: int):
#     start_time = int(request.form["start_time"])
#     duration = request.form["duration"]
#     video_url = get_video(video_id).get_url()
#     logger.info(f"Fetching clip for {int(start_time)}")
#     if video_url is not None:
#         clip = get_yt_segment(video_url, int(start_time), int(duration))
#         return send_file(
#             clip,
#             mimetype="video/mp4",
#             download_name=f"{video_id}.mp4",
#         )
#     return "something went wrong sorry no error handling glhf"


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


@app.route("/video/<int:video_id>/upload_transcription", methods=["POST"])
def upload_transcription(video_id: int):
    logger.info(f"ready to receive json on {video_id}")
    video = get_video(video_id)
    if request.json is None:
        logger.error("Json not found in request")
        return "something wrong", 500
    filename = f"{video_id}.json"
    filepath = os.path.join(config.cache_location, filename)
    if os.path.exists(filepath):
        os.remove(filepath)
    logger.info(f"Json will be saved to{filepath}")
    data = TranscriptionResult.model_validate(request.get_json())
    db.session.add(
        Transcription(
            video_id=video.id,
            language=data.language,
            file_extention="json",
            file=json.dumps(request.get_json()).encode("utf-8"),
            source=TranscriptionSource.Unknown,
        )
    )
    db.session.commit()
    logger.info("File uploaded")
    return "ok", 200


@app.route("/transcription/<int:transcription_id>/delete_wordmaps")
@login_required
def delete_wordmaps_transcription(transcription_id: int):
    transcription = get_transcription(transcription_id)
    transcription.delete_attached_wordmaps()
    return redirect(request.referrer)


@app.route("/transcription/<int:transcription_id>/delete")
@login_required
def delete_transcription(transcription_id: int):
    transcription = get_transcription(transcription_id)
    transcription.delete()
    return redirect(request.referrer)
