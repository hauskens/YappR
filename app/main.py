from sqlalchemy import select
from sqlalchemy_file.storage import StorageManager
from libcloud.storage.drivers.local import LocalStorageDriver
from flask import Flask, flash, render_template, request, redirect, url_for, send_file
from celery import Celery, Task
from flask_bootstrap import Bootstrap5
from models.db import (
    Broadcaster,
    Platforms,
    Segments,
    WordMaps,
    VideoType,
    Channels,
    Video,
    Transcription,
    db,
)
from models.config import Config
from parse import parse_vtt
import logging
from os import makedirs
from tasks import (
    get_yt_videos,
    save_largest_thumbnail,
)
import io
from retrievers import (
    get_broadcasters,
    get_platforms,
    get_broadcaster_channels,
    get_channel,
    get_video,
    get_video_by_channel,
    get_video_by_ref,
    get_transcriptions_by_video,
    get_transcription,
    search_wordmaps_by_transcription,
    get_segments_by_wordmap,
    fetch_transcription,
    fetch_audio,
)


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
app = Flask(__name__)
bootstrap = Bootstrap5(app)
config = Config()
app.secret_key = config.app_secret
app.config["SQLALCHEMY_DATABASE_URI"] = config.database_uri
app.config["CELERY"] = dict(
    broker_url=config.redis_uri, backend=config.database_uri, task_ignore_result=True
)
# db = SQLAlchemy(app, model_class=Base)
db.init_app(app)
celery = celery_init_app(app)
logger = logging.getLogger(__name__)
logging.basicConfig(level=config.log_level)
init_storage()
container = LocalStorageDriver(config.storage_location).get_container("transcriptions")
StorageManager.add_storage("default", container)

with app.app_context():
    db.create_all()
    pf = get_platforms()
    if pf is not None:
        if len(pf) == 0:
            yt = Platforms(name="YouTube", url="https://youtube.com")
            twitch = Platforms(name="Twitch", url="https://twitch.tv")
            db.session.add_all([yt, twitch])
            db.session.commit()


@app.route("/")
def index():
    broadcasters = get_broadcasters()
    logger.info("Loaded search.html")
    return render_template("search.html", broadcasters=broadcasters)


@app.route("/chart")
def chart():
    logger.info("Loaded chart.html")
    channel = get_channel(2)
    return render_template("chart.html", channel=channel)


@app.route("/broadcasters")
def broadcasters():
    broadcasters = get_broadcasters()
    logger.info("Loaded broadcasters.html")
    return render_template("broadcasters.html", broadcasters=broadcasters)


@app.route("/search")
def search_page():
    broadcasters = get_broadcasters()
    logger.info("Loaded search.html")
    return render_template("search.html", broadcasters=broadcasters)


@app.route("/search", methods=["POST"])
def search_word():
    logger.info("Loaded search_word.html")
    search_term = request.form["search"]
    broadcaster_id = request.form["broadcaster"]
    broadcaster = get_broadcaster(int(broadcaster_id))
    if broadcaster is None:
        raise ValueError("Broadcaster not found")
    logger.info(f"Searching for '{search_term}' on {broadcaster.name}")
    channels = get_broadcaster_channels(int(broadcaster_id))
    transcriptions: list[Transcription] = []
    video_result: list[Video] = []
    wordmap_result: list[WordMaps] = []
    segment_result: list[Segments] = []
    if channels is None:
        return "Channels not found, i have not implemented proper error sorry.."
    for channel in channels:
        for video in channel.videos:
            transcriptions += video.transcriptions
    search_words = search_term.lower().split()
    for t in transcriptions:
        search_result = search_wordmaps_by_transcription(search_words[0], t)
        for wordmap in search_result:
            wordmap_result.append(wordmap)
            video_result.append(wordmap.transcription.video)

    for wordmap in wordmap_result:
        segment_result += get_segments_by_wordmap(wordmap)
    logger.info(f"Search found {len(video_result)}")
    return render_template(
        "result.html",
        search_word=search_term,
        broadcaster=broadcaster,
        video_result=video_result,
        segment_result=segment_result,
    )


@app.route("/thumbnails/<int:video_id>")
def serve_thumbnails(video_id: int):
    video = get_video(video_id)
    content = video.thumbnail.file.read()
    return send_file(
        io.BytesIO(content),
        mimetype="image/jpeg",
        download_name=f"{video.id}.jpg",
    )


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
    abt = Platforms(name=name, url=url)
    db.session.add(abt)
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
                thumbnail = save_largest_thumbnail(video)
                existing_video = get_video_by_ref(video.id)
                if existing_video is None:
                    if thumbnail is not None:
                        db.session.add(
                            Video(
                                title=video.title,
                                video_type=VideoType.VOD,
                                channel_id=channel.id,
                                platform_ref=video.id,
                                duration=video.duration,
                                thumbnail=open(thumbnail, "rb"),
                            )
                        )
                    else:
                        # this is reduntant, can be done much more pretty i guess, but im lazy rn
                        db.session.add(
                            Video(
                                title=video.title,
                                video_type=VideoType.VOD,
                                channel_id=channel.id,
                                platform_ref=video.id,
                                duration=video.duration,
                            )
                        )

                else:
                    existing_video.title = video.title
                    existing_video.duration = video.duration
                    if thumbnail is not None:
                        existing_video.thumbnail = open(thumbnail, "rb")
        db.session.commit()
    return redirect(url_for("channel_get_videos", id=id))


@celery.task
def task_fetch_transcription(video_id: int):
    logger.info(f"Task queued, fetching transcription for {video_id}")
    fetch_transcription(video_id)


@celery.task
def task_audio(video_id: int):
    logger.info(f"Task queued, fetching audio for {video_id}")
    fetch_audio(video_id)


@celery.task
def task_parse_transcription(transcription_id: int):
    tran = get_transcription(transcription_id)
    if tran is not None:
        logger.info(f"Task queued, parsing transcription for {transcription_id}")
        content = tran.file.file.read()
        _ = parse_vtt(
            db=db, vtt_buffer=io.BytesIO(content), transcription_id=transcription_id
        )


@app.route("/channel/<int:id>/fetch_audio")
def channel_fetch_audio(id: int):
    channel = get_channel(id)
    logger.info(f"Fetching all audio for {channel.name}")
    for video in channel.videos:
        _ = task_audio.delay(video.id)
    return redirect(url_for("channel_get_videos", id=id))


# todo: send some confirmation to user that task is queued and prevent new queue from getting started
@app.route("/channel/<int:id>/fetch_transcriptions")
def channel_fetch_transcriptions(id: int):
    channel = get_channel(id)
    logger.info(f"Fetching all transcriptions for {channel.name}")
    for video in channel.videos:
        _ = task_fetch_transcription.delay(video.id)
    return redirect(url_for("channel_get_videos", id=id))


@app.route("/channel/<int:id>/parse_transcriptions")
def channel_parse_transcriptions(id: int):
    videos = get_video_by_channel(id)
    if videos is not None:
        for video in videos:
            transcriptions = get_transcriptions_by_video(video.id)
            if transcriptions is not None and len(transcriptions) > 0:
                # todo: ensure only YT transcriptions are processed
                for tran in transcriptions:

                    _ = task_parse_transcription.delay(tran.id)
    return redirect(url_for("channel_get_videos", id=id))


@app.route("/video/<int:id>/fetch_transcriptions")
def video_fetch_transcriptions(id: int):
    logger.info(f"Fetching transcriptions for {id}")
    fetch_transcription(id)
    return redirect(url_for("video_get_transcriptions", id=id))


@app.route("/video/<int:id>/get_transcriptions")
def video_get_transcriptions(id: int):
    return render_template(
        "video_edit.html",
        transcriptions=get_transcriptions_by_video(id),
        video=get_video(id),
    )


@app.route("/video/<int:video_id>/parse_transcriptions")
def video_parse_transcriptions(video_id: int):
    tran = get_transcriptions_by_video(video_id)
    if tran is not None:
        for t in tran:
            _ = task_parse_transcription.delay(t.id)
    return render_template(
        "video_edit.html",
        transcriptions=get_transcriptions_by_video(video_id),
        video=get_video(video_id),
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
    return "file not found!", 404


@app.route("/transcription/<int:id>/parse")
def parse_transcription(id: int):
    transcription = get_transcription(id)
    if transcription is not None:
        content = transcription.file.file.read()
        _ = parse_vtt(db=db, vtt_buffer=io.BytesIO(content), transcription_id=id)
    return "buh"


if __name__ == "__main__":
    app.run(debug=True, host=config.app_host, port=config.app_port)
