from sqlalchemy import select
from flask_login import current_user, login_required
from flask import (
    Flask,
    flash,
    render_template,
    request,
    redirect,
    url_for,
    send_file,
    send_from_directory,
    g,
)

from celery import Celery, Task
from .models.db import (
    Broadcaster,
    Platforms,
    VideoType,
    Channels,
    PermissionType,
    db,
)
from .repository import Channel, save_transcription
from .models.config import config
from .parse import parse_vtt
import logging
from .tasks import (
    get_yt_segment,
)
import io
from .retrievers import *
from .search import search, search_date
from . import create_app, login_manager


def celery_init_app(app: Flask) -> Celery:
    # todo: getting a type error here
    class FlaskTask(Task):
        def __call__(self, *args: object, **kwargs: object) -> object:
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_app = Celery(app.name, task_cls=FlaskTask)
    celery_app.config_from_object(app.config["CELERY"])
    celery_app.set_default()
    app.extensions["celery"] = celery_app
    return celery_app


app = create_app()

celery = celery_init_app(app)
logger = logging.getLogger(__name__)
logging.basicConfig(level=config.log_level)


# @app.route("/admin")
# def access_denied():
#     return send_from_directory("static", "404.jpg")


@app.before_request
def get_current_user():
    if current_user.is_authenticated and "username" not in g:
        g.user_object = current_user
        g.username = current_user.name
        g.avatar_url = current_user.avatar_url


@app.route("/")
@login_required
def index():
    broadcasters = get_broadcasters()
    logger.info("Loaded search.html")
    return render_template("search.html", broadcasters=broadcasters)


@app.route("/users")
@login_required
def users():
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
        _ = add_permissions(user, PermissionType[permission_name])
        users = get_users()
        return render_template(
            "users.html", users=users, permission_types=PermissionType
        )
    else:
        return access_denied()


@login_manager.unauthorized_handler
def redirect_unauthorized():
    return render_template("unauthorized.html")


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


@app.route("/broadcasters")
@login_required
def broadcasters():
    broadcasters = get_broadcasters()
    logger.info("Loaded broadcasters.html")
    return render_template("broadcasters.html", broadcasters=broadcasters)


@app.route("/search")
@login_required
def search_page():
    broadcasters = get_broadcasters()
    logger.info("Loaded search.html")
    return render_template("search.html", broadcasters=broadcasters)


@app.route("/search", methods=["POST"])
@login_required
def search_word():
    logger.info("Loaded search_word.html")
    search_term = request.form["search"]
    broadcaster_id = request.form["broadcaster"]
    start_date = get_valid_date(request.form["start_date"])
    end_date = get_valid_date(request.form["end_date"])
    broadcaster = get_broadcaster(int(broadcaster_id))
    if broadcaster is None:
        raise ValueError("Broadcaster not found")
    add_log(f"Searching for '{search_term}' on {broadcaster.name}")
    channels = get_broadcaster_channels(int(broadcaster_id))
    if channels is None:
        return "Channels not found, i have not implemented proper error sorry.."
    if start_date is not None and end_date is not None:
        logger.info(f"Found a date, start {start_date} end {end_date}")
        segment_result, video_result = search_date(
            search_term, int(broadcaster_id), start_date, end_date
        )
    else:
        segment_result, video_result = search(search_term, int(broadcaster_id))
    if len(segment_result) == 0:
        flash(
            "Could not find any videos based on that search, try something else",
            "error",
        )
        return render_template("search.html", broadcasters=get_broadcasters())

    return render_template(
        "result.html",
        search_word=search_term,
        broadcaster=broadcaster,
        video_result=video_result,
        segment_result=segment_result,
    )


@app.route("/thumbnails/<int:video_id>")
@login_required
def serve_thumbnails(video_id: int):
    video = get_video(video_id)
    content = video.thumbnail.file.read()
    return send_file(
        io.BytesIO(content),
        mimetype="image/jpeg",
        download_name=f"{video.id}.jpg",
    )


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
    broadcaster = (
        db.session.execute(select(Broadcaster).filter_by(id=id)).scalars().one()
    )
    channels = get_broadcaster_channels(id)
    return render_template(
        "broadcaster_edit.html",
        broadcaster=broadcaster,
        channels=channels,
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
    channel = Channel(channel_id)
    _ = channel.delete()
    db.session.commit()
    return "ok"


@app.route("/channel/<int:channel_id>/get_videos")
@login_required
def channel_get_videos(channel_id: int):
    channel = Channel(channel_id).db_ref
    videos = get_video_by_channel(channel_id=channel.id)
    return render_template("channel_edit.html", videos=videos, channel=channel)


@app.route("/channel/<int:channel_id>/fetch_details")
@login_required
def channel_fetch_details(channel_id: int):
    channel = Channel(channel_id)
    channel.update()
    return render_template(
        "broadcaster_edit.html",
        broadcaster=channel.db_ref.broadcaster_id,
        channels=get_broadcaster_channels(broadcaster_id=channel.db_ref.broadcaster_id),
        platforms=get_platforms(),
        video_types=VideoType,
    )


@app.route("/channel/<int:id>/fetch_videos")
@login_required
def channel_fetch_videos(id: int):
    channel = Channel(id)
    logger.info(f"Fetching videos for {channel.db_ref.name}")
    channel.fetch_latest_videos()
    return redirect(url_for("channel_get_videos", channel_id=channel.db_ref.id))


@celery.task
def task_fetch_transcription(video_id: int):
    logger.info(f"Task queued, fetching transcription for {video_id}")
    save_transcription(video_id)


@celery.task
def task_audio(video_id: int):
    logger.info(f"Task queued, fetching audio for {video_id}")
    fetch_audio(video_id)


@celery.task
def task_parse_transcription(transcription_id: int):
    tran = get_transcription(transcription_id)
    logger.info(f"Task queued, parsing transcription for {transcription_id}")
    if tran.word_maps is not None:
        logger.debug(f"wordmaps already found, deleting {id}")
        _ = delete_wordmaps_on_transcription(transcription_id)
        db.session.flush()
    content = tran.file.file.read()
    _ = parse_vtt(
        db=db, vtt_buffer=io.BytesIO(content), transcription_id=transcription_id
    )


@app.route("/channel/<int:id>/fetch_audio")
@login_required
def channel_fetch_audio(id: int):
    channel = Channel(id).db_ref
    logger.info(f"Fetching all audio for {channel.name}")
    for video in channel.videos:
        _ = task_audio.delay(video.id)
    return redirect(url_for("channel_get_videos", channel_id=channel.id))


# todo: send some confirmation to user that task is queued and prevent new queue from getting started
@app.route("/channel/<int:id>/fetch_transcriptions")
@login_required
def channel_fetch_transcriptions(id: int):
    channel = Channel(id).db_ref
    logger.info(f"Fetching all transcriptions for {channel.name}")
    for video in channel.videos:
        _ = task_fetch_transcription.delay(video.id)
    return redirect(url_for("channel_get_videos", channel_id=channel.id))


@app.route("/channel/<int:id>/parse_transcriptions")
@login_required
def channel_parse_transcriptions(id: int):
    channel = Channel(id).db_ref
    videos = get_video_by_channel(id)
    if videos is not None:
        for video in videos:
            transcriptions = get_transcriptions_by_video(video.id)
            if transcriptions is not None and len(transcriptions) > 0:
                # todo: ensure only YT transcriptions are processed
                for tran in transcriptions:
                    _ = task_parse_transcription.delay(tran.id)
    return redirect(url_for("channel_get_videos", channel_id=channel.id))


@app.route("/video/<int:id>/fetch_transcriptions")
@login_required
def video_fetch_transcriptions(id: int):
    logger.info(f"Fetching transcriptions for {id}")
    save_transcription(id)
    return redirect(url_for("video_get_transcriptions", id=id))


@app.route("/video/<int:id>/get_transcriptions")
@login_required
def video_get_transcriptions(id: int):
    return render_template(
        "video_edit.html",
        transcriptions=get_transcriptions_by_video(id),
        video=get_video(id),
    )


@app.route("/video/<int:video_id>/parse_transcriptions")
@login_required
def video_parse_transcriptions(video_id: int):
    tran = get_transcriptions_by_video(video_id)
    if tran is not None:
        for t in tran:
            if t.word_maps is not None:
                logger.debug(f"wordmaps already found, deleting {id}")
                _ = delete_wordmaps_on_transcription(t.id)
                db.session.flush()
    return render_template(
        "video_edit.html",
        transcriptions=get_transcriptions_by_video(video_id),
        video=get_video(video_id),
    )


@app.route("/video/<int:video_id>/download_clip", methods=["POST"])
@login_required
def download_video_clip(video_id: int):
    start_time = int(request.form["start_time"])
    duration = request.form["duration"]
    video_url = get_video(video_id).get_url()
    logger.info(f"Fetching clip for {int(start_time)}")
    if video_url is not None:
        clip = get_yt_segment(video_url, int(start_time), int(duration))
        return send_file(
            clip,
            mimetype="video/mp4",
            download_name=f"{video_id}.mp4",
        )
    return "something went wrong sorry no error handling glhf"


@app.route("/transcription/<int:id>/download")
@login_required
def download_transcription(id: int):
    transcription = get_transcription(id)
    content = transcription.file.file.read()
    return send_file(
        io.BytesIO(content),
        mimetype="text/plain",
        download_name=f"{transcription.id}.{transcription.file_extention}",
    )


@app.route("/transcription/<int:transcription_id>/parse")
@login_required
def parse_transcription(transcription_id: int):
    transcription = get_transcription(transcription_id)
    if transcription.word_maps is not None:
        logger.debug(f"wordmaps already found, deleting {id}")
        _ = delete_wordmaps_on_transcription(transcription_id)
        db.session.flush()
    content = transcription.file.file.read()
    _ = parse_vtt(
        db=db, vtt_buffer=io.BytesIO(content), transcription_id=transcription_id
    )
    return redirect(url_for("video_get_transcriptions", id=transcription.video_id))


@app.route("/transcription/<int:transcription_id>/delete_wordmaps")
@login_required
def delete_wordmaps_transcription(transcription_id: int):
    transcription = get_transcription(transcription_id)
    _ = delete_wordmaps_on_transcription(transcription_id)
    db.session.commit()
    return redirect(url_for("video_get_transcriptions", id=transcription.video_id))


if __name__ == "__main__":
    app.run(debug=config.debug, host=config.app_host, port=config.app_port)
