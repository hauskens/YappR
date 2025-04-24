from flask_login import current_user, login_required
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    g,
)

from celery import Celery, Task, shared_task
from .models.db import (
    PermissionType,
)
import requests
import os
from .transcribe import transcribe
from .models.config import config
import logging
from .retrievers import get_transcription, get_video, fetch_audio
from .routes import *
from . import app, login_manager, init_storage


def celery_init_app(app: Flask) -> Celery:
    # todo: getting a type error here
    class FlaskTask(Task):
        def __call__(self, *args: object, **kwargs: object) -> object:
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_app = Celery(app.name, task_cls=FlaskTask)
    celery_app.config_from_object(app.config["CELERY"])
    celery_app.set_default()
    celery_app.autodiscover_tasks()
    app.extensions["celery"] = celery_app
    return celery_app


celery = celery_init_app(app)
logger = logging.getLogger(__name__)
logging.basicConfig(level=config.log_level)


@app.before_request
def get_current_user():
    try:
        if current_user.is_authenticated and "username" not in g:
            g.user_object = current_user
            g.username = current_user.name
            g.avatar_url = current_user.avatar_url
    except:
        logger.info("get_current_user: failed")


@login_manager.unauthorized_handler
def redirect_unauthorized():
    return render_template("unauthorized.html")


@app.route("/video/<int:video_id>/process_audio")
@login_required
def video_process_audio(video_id: int):
    logger.info(f"Processing audio for {video_id}")
    _ = task_transcribe_audio.delay(video_id)
    return redirect(request.referrer)


@app.route("/video/<int:video_id>/fecth_audio")
@login_required
def video_fetch_audio(video_id: int):
    logger.info(f"Fetching audio for {video_id}")
    _ = task_fetch_audio.delay(video_id)
    return redirect(request.referrer)


@celery.task()
def task_fetch_audio(video_id: int):
    logger.info(f"Fetching audio for {video_id}")
    _ = task_audio(video_id)


@celery.task()
def task_fetch_transcription(video_id: int):
    video = get_video(video_id)
    logger.info(f"Task queued, fetching transcription for {video.title}")
    _ = video.save_transcription()


@celery.task
def task_audio(video_id: int):
    logger.info(f"Task queued, fetching audio for {video_id}")
    video = get_video(video_id)
    video.save_audio()


@celery.task
def task_transcribe_audio(video_id: int, force: bool = False):
    video = get_video(video_id)
    logger.info(f"Task queued, processing audio for {video_id}")
    local_filename = config.cache_location + f"/{video.id}.mp4"
    if os.path.exists(local_filename):
        os.remove(local_filename)
    if video.audio is not None:
        with requests.get(f"{config.app_url}/video/{video.id}/download_audio") as r:
            r.raise_for_status()
            with open(local_filename, "wb") as f:
                _ = f.write(r.content)
            try:
                file_content = transcribe(local_filename)
                logger.info(f"Uploading to video {video_id}")
                headers = {"Content-type": "application/json", "Accept": "text/plain"}
                r = requests.post(
                    f"{config.app_url}/video/{video_id}/upload_transcription",
                    json=file_content,
                    headers=headers,
                )
            except:
                raise ValueError("Failed to upload audio file")


@celery.task
def task_parse_transcription(transcription_id: int, force: bool = False):
    trans = get_transcription(transcription_id)
    trans.process_transcription(force)


@app.route("/transcription/<int:transcription_id>/parse")
@login_required
def parse_transcription(transcription_id: int):
    _ = task_parse_transcription.delay(transcription_id)
    return redirect(request.referrer)


# todo: send some confirmation to user that task is queued and prevent new queue from getting started
@app.route("/channel/<int:channel_id>/fetch_transcriptions")
@login_required
def channel_fetch_transcriptions(channel_id: int):
    if current_user.has_permission(PermissionType.Admin):
        channel = get_channel(channel_id)
        logger.info(f"Fetching all transcriptions for {channel.name}")
        for video in channel.videos:
            _ = task_fetch_transcription.delay(video.id)
    return redirect(request.referrer)


@app.route("/channel/<int:channel_id>/parse_transcriptions")
@login_required
def channel_parse_transcriptions(channel_id: int):
    if current_user.has_permission(PermissionType.Admin):
        channel = get_channel(channel_id)
        for video in channel.videos:
            for tran in video.transcriptions:
                _ = task_parse_transcription.delay(tran.id)
    return redirect(request.referrer)


if __name__ == "__main__":
    app.run(debug=config.debug, host=config.app_host, port=config.app_port)
