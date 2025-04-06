from collections.abc import Sequence
from sqlalchemy import select
from sqlalchemy_file.storage import StorageManager
from libcloud.storage.drivers.local import LocalStorageDriver
from flask import Flask, flash, render_template, request, redirect, url_for, send_file
from flask_sqlalchemy import SQLAlchemy
from celery import Celery
from models.db import (
    Base,
    Broadcaster,
    Platforms,
    VideoType,
    Channels,
    Video,
    Transcription,
    TranscriptionSource,
)
from models.config import Config
from parse import parse_vtt
from datetime import datetime
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


def fetch_transcription(video_id: int):
    tmpdir = tempfile.mkdtemp()
    video = get_video(video_id)
    video_url = video.get_url()
    if video_url is not None:
        logger.info(f"fetching transcription for {video_id}")
        subtitles = get_yt_video_subtitles(video_url, tmpdir)
        for sub in subtitles:
            logger.info(
                f"checking if transcriptions exists on {video_id}, {len(video.transcriptions)}"
            )
            if len(video.transcriptions) == 0:
                logger.info(f"transcriptions not found on {video_id}, adding new..")
                db.session.add(
                    Transcription(
                        video_id=video_id,
                        language=sub.language,
                        file_extention=sub.extention,
                        file=open(sub.path, "rb"),
                        source=TranscriptionSource.YouTube,
                    )
                )
            else:
                logger.info(f"transcriptions found on {video_id}, updating existing..")
                for t in video.transcriptions:
                    logger.info(
                        f"transcriptions found on {video_id} with platform {t.source}"
                    )
                    if t.source == TranscriptionSource.YouTube:
                        t.file = open(sub.path, "rb")
                        t.file_extention = sub.extention
                        t.language = sub.language
                        t.last_updated = datetime.now()

        db.session.commit()


def init_storage(container: str = "transcriptions"):
    makedirs(
        config.storage_location + "/" + container, 0o777, exist_ok=True
    )  # Ensure storage folder exists


def init_platforms():
    if get_platforms() is None:
        yt = Platforms(name="YouTube", url="https://youtube.com")
        twitch = Platforms(name="Twitch", url="https://twitch.tv")
        db.session.add_all([yt, twitch])
        db.session.commit()


from celery import Task


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


# holy... need to clean up this..
db = SQLAlchemy(model_class=Base)
app = Flask(__name__)
config = Config()
app.secret_key = config.app_secret
app.config["SQLALCHEMY_DATABASE_URI"] = config.database_uri
app.config["CELERY"] = dict(broker_url=config.redis_uri, task_ignore_result=True)
celery = celery_init_app(app)
logger = logging.getLogger(__name__)
logging.basicConfig(level=config.log_level)
init_storage()
container = LocalStorageDriver(config.storage_location).get_container("transcriptions")
StorageManager.add_storage("default", container)

db.init_app(app)
with app.app_context():
    db.create_all()
    # pf = get_platforms()
    # yt = Platforms(name="YouTube", url="https://youtube.com")
    # twitch = Platforms(name="Twitch", url="https://twitch.tv")
    # db.session.add_all([yt, twitch])
    # db.session.commit()


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
                existing_video = get_video_by_ref(video.id)
                if existing_video is None:
                    db.session.add(
                        Video(
                            title=video.title,
                            video_type=channel.main_video_type,
                            channel_id=channel.id,
                            platform_ref=video.id,
                            duration=video.duration,
                        )
                    )
                else:
                    existing_video.title = video.title
                    existing_video.duration = video.duration
        db.session.commit()
    return redirect(url_for("channel_get_videos", id=id))


@celery.task
def task_fetch_transcription(video_id: int):
    logger.info(f"Task queued, fetching transaction for {video_id}")
    fetch_transcription(video_id)


# todo: send some confirmation to user that task is queued and prevent new queue from getting started
@app.route("/channel/<int:id>/fetch_transcriptions")
def channel_fetch_transcriptions(id: int):
    channel = get_channel(id)
    logger.info(f"Fetching all transcriptions for {channel.name}")
    for video in channel.videos:
        _ = task_fetch_transcription.delay(video.id)
    return redirect(url_for("channel_get_videos", id=id))


@app.route("/video/<int:id>/fetch_transcriptions")
def video_fetch_transcriptions(id: int):
    fetch_transcription(id)
    return redirect(url_for("video_get_transcriptions", id=id))


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


# @app.route("/transcription/<int:id>/parse")
# def parse_transcription(id: int):
#     transcription = get_transcription(id)
#     if transcription is not None:
#         content = transcription.file.file.read()
#         test = parse_vtt(io.BytesIO(content))
#         # return send_file(
#         #     io.BytesIO(content),
#         #     mimetype="text/plain",
#         #     download_name=f"{transcription.id}.{transcription.file_extention}",
#         # )
#     return "buh"


if __name__ == "__main__":
    app.run(debug=True)
