from collections.abc import Sequence
from sqlalchemy import select
from sqlalchemy_file.storage import StorageManager
from libcloud.storage.drivers.local import LocalStorageDriver
from flask import Flask, flash, render_template, request, redirect, url_for, send_file
from flask_sqlalchemy import SQLAlchemy
from models.db import (
    Base,
    Broadcaster,
    Platforms,
    VideoType,
    Channels,
    Video,
    Transcription,
)
from models.config import Config
import logging
from os import makedirs
from tasks import get_yt_videos, get_yt_video_subtitles
import tempfile
import io


def get_broadcasters() -> Sequence[Broadcaster]:
    return (
        db.session.execute(select(Broadcaster).order_by(Broadcaster.id)).scalars().all()
    )


def get_platforms() -> Sequence[Platforms] | None:
    return db.session.execute(select(Platforms)).scalars().all()


def get_broadcaster_channels(broadcaster_id: int) -> Sequence[Channels] | None:
    return (
        db.session.execute(select(Channels).filter_by(broadcaster_id=broadcaster_id))
        .scalars()
        .all()
    )


def get_channel(channel_id: int) -> Channels:
    return db.session.execute(select(Channels).filter_by(id=channel_id)).scalars().one()


def get_video(video_id: int) -> Video:
    return db.session.execute(select(Video).filter_by(id=video_id)).scalars().one()


def get_video_by_channel(channel_id: int) -> Sequence[Video] | None:
    return (
        db.session.execute(select(Video).filter_by(channel_id=channel_id))
        .scalars()
        .all()
    )


def get_video_by_ref(video_platform_ref: str) -> Video | None:
    return (
        db.session.execute(select(Video).filter_by(platform_ref=video_platform_ref))
        .scalars()
        .one_or_none()
    )


def get_transcriptions_by_video(video_id: int) -> Sequence[Transcription] | None:
    return (
        db.session.execute(select(Transcription).filter_by(video_id=video_id))
        .scalars()
        .all()
    )


def get_transcription(id: int) -> Transcription | None:
    return (
        db.session.execute(select(Transcription).filter_by(id=id))
        .scalars()
        .one_or_none()
    )


def init_storage(container: str = "transcriptions"):
    makedirs(
        config.storage_location + "/" + container, 0o777, exist_ok=True
    )  # Ensure storage folder exists


db = SQLAlchemy(model_class=Base)
app = Flask(__name__)
config = Config()
app.secret_key = config.app_secret
app.config["SQLALCHEMY_DATABASE_URI"] = config.database_uri
logger = logging.getLogger(__name__)
logging.basicConfig(level=config.log_level)
init_storage()
container = LocalStorageDriver(config.storage_location).get_container("transcriptions")
StorageManager.add_storage("default", container)

db.init_app(app)
with app.app_context():
    db.create_all()


@app.route("/")
def index():
    logger.info("Loaded index.html")
    return render_template("index.html")


@app.route("/broadcasters")
def broadcasters():
    broadcasters = get_broadcasters()
    logger.info("Loaded broadcasters.html")
    return render_template("broadcasters.html", broadcasters=broadcasters)


@app.route("/platforms")
def platforms():
    platforms = get_platforms()
    logger.info("Loaded platforms.html")
    return render_template("platforms.html", platforms=platforms)


@app.route("/broadcaster/create", methods=["POST"])
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
    db.session.add(Platforms(name=name, url=url))
    db.session.commit()
    return redirect(url_for("platforms"))


@app.route("/channel/create", methods=["POST"])
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


@app.route("/channel/<int:id>/get_videos")
def channel_get_videos(id: int):
    videos = get_video_by_channel(channel_id=id)
    return render_template("channel_edit.html", videos=videos, channel=get_channel(id))


@app.route("/channel/<int:id>/fetch_videos")
def channel_fetch_videos(id: int):
    channel = get_channel(id)
    url = channel.get_url()
    logger.info(f"Fetching videos for {channel.name} using url: {url}")
    if channel.platform.name.lower() == "youtube" and url is not None:
        channel_videos = get_yt_videos(channel_url=url)
        if channel_videos is not None:
            for video in channel_videos:
                if get_video_by_ref(video.id) is None:
                    db.session.add(
                        Video(
                            title=video.title,
                            video_type=channel.main_video_type,
                            channel_id=channel.id,
                            platform_ref=video.id,
                            duration=video.duration,
                        )
                    )
        db.session.commit()
    return render_template(
        "channel_edit.html", videos=get_video_by_channel(id), channel=get_channel(id)
    )


@app.route("/video/<int:id>/fetch_transcriptions")
def video_fetch_transcriptions(id: int):
    tmpdir = tempfile.mkdtemp()
    video_url = get_video(id).get_url()
    if video_url is not None:
        subtitles = get_yt_video_subtitles(video_url, tmpdir)
        for sub in subtitles:
            db.session.add(
                Transcription(
                    video_id=id,
                    language=sub.language,
                    file_extention=sub.extention,
                    file=open(sub.path, "rb"),
                )
            )
        db.session.commit()
    return render_template(
        "video_edit.html",
        transcriptions=get_transcriptions_by_video(id),
        video=get_video(id),
    )


@app.route("/video/<int:id>/get_transcriptions")
def video_get_transcriptions(id: int):
    return render_template(
        "video_edit.html",
        transcriptions=get_transcriptions_by_video(id),
        video=get_video(id),
    )


@app.route("/transcription/<int:id>/download")
def download_transcription(id: int):
    transcription = get_transcription(id)
    if transcription is not None:
        content = transcription.file.file.read()
        return send_file(
            io.BytesIO(content),
            mimetype="text/plain",
            download_name=f"{transcription.id}.{transcription.file_extention}",
        )


if __name__ == "__main__":
    app.run(debug=True)
