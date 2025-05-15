from flask_login import current_user, login_required
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    jsonify,
    g,
)
import time
import redis
import json
from celery import Celery, Task, group, chain
from .models.db import (
    PermissionType,
)
import requests
import os
from .transcribe import transcribe
from .models.config import config
import logging
from .retrievers import get_transcription, get_video
from .routes import *
from . import app, login_manager
from .models.db import TranscriptionSource
from .utils import require_api_key




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
r = redis.Redis.from_url(config.redis_uri)
logger = logging.getLogger(__name__)
logging.basicConfig(level=config.log_level)

@app.errorhandler(429)
def ratelimit_handler(e):
    return render_template("unauthorized.html", ratelimit_exceeded=e.description)


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


@app.route("/video/<int:video_id>/process_full")
@login_required
def video_process_full(video_id: int):
    if current_user.has_permission(PermissionType.Admin) or current_user.has_permission(
        PermissionType.Moderator
    ):
        logger.info(f"Full processing of video: {video_id}")
        video = get_video(video_id)
        if video.channel.platform.name.lower() == "twitch":
            logger.info(f"Using twitch pipeline: {video_id}")
            _ = group(
                task_fetch_audio.delay(video_id),
                task_transcribe_audio.delay(video_id),
                task_parse_video_transcriptions.delay(video_id, force=True),
            )
        elif video.channel.platform.name.lower() == "youtube":
            logger.info(f"Using youtube pipeline: {video_id}")
            _ = group(
                task_fetch_transcription.delay(video_id),
                task_parse_video_transcriptions.delay(video_id, force=True),
            )
        return redirect(request.referrer)
    else:
        return access_denied()


@app.route("/video/<int:video_id>/fecth_audio")
@login_required
def video_fetch_audio(video_id: int):
    logger.info(f"Fetching audio for {video_id}")
    _ = chain(task_fetch_audio.s(video_id), task_transcribe_audio.s(), task_parse_video_transcriptions.s()).apply_async()

    return redirect(request.referrer)


@app.route("/celery/active-view")
@login_required
def celery_active_tasks_view():
    i = celery.control.inspect()
    active = i.active() or {}
    queue_names = ["gpu-queue", "celery"]
    queued_tasks_by_queue = {}
    for queue_name in queue_names:
        queued_tasks = []
        queue_length = r.llen(queue_name)
        for i in range(queue_length):
            task_data = r.lindex(queue_name, i)
            if task_data:
                task = json.loads(task_data)
                # Extract useful info
                headers = task.get("headers", {})
                task_name = headers.get("task", "Unknown Task")
                argsrepr = headers.get("argsrepr", "")
                queued_tasks.append(
                    {
                        "raw": task,
                        "task_name": task_name,
                        "argsrepr": argsrepr,
                    }
                )
        queued_tasks_by_queue[queue_name] = queued_tasks
    return render_template(
        "active_tasks.html",
        active_tasks=active,
        queued_tasks_by_queue=queued_tasks_by_queue,
    )


@celery.task()
def task_fetch_audio(video_id: int):
    logger.info(f"Fetching audio for {video_id}")
    video = get_video(video_id)
    video.save_audio()
    return video_id


@celery.task()
def task_fetch_transcription(video_id: int):
    video = get_video(video_id)
    logger.info(f"Task queued, fetching transcription for {video.title}")
    _ = video.download_transcription()
    return video_id


@celery.task
def task_transcribe_audio(video_id: int, force: bool = False):
    headers = {
        "X-API-Key": config.api_key
    }
    video = get_video(video_id)
    for t in video.transcriptions:
        if t.source == TranscriptionSource.Unknown and force == False:
            logger.info(f"Transcription already exists on video {video.id}, skipping")
            return
        if t.source == TranscriptionSource.Unknown and force:
            logger.info(f"Transcription already exists on video {video.id}, deleting")
            t.delete()
    logger.info(f"Task queued, processing audio for {video_id}")
    local_filename = config.cache_location + f"/{video.id}.mp4"
    if os.path.exists(local_filename):
        os.remove(local_filename)
    if video.audio is not None:
        with requests.get(f"{config.app_url}/video/{video.id}/download_audio", headers=headers) as r:
            r.raise_for_status()
            with open(local_filename, "wb") as f:
                _ = f.write(r.content)
            try:
                file_content = transcribe(local_filename)
                logger.info(f"Uploading to video {video_id}")
                headers = {"Content-type": "application/json", "Accept": "text/plain", "X-API-Key": config.api_key}
                r = requests.post(
                    f"{config.app_url}/video/{video_id}/upload_transcription",
                    json=file_content,
                    headers=headers,
                )
            except:
                raise ValueError("Failed to upload audio file")
    return video_id


@celery.task
def task_parse_transcription(transcription_id: int, force: bool = False):
    trans = get_transcription(transcription_id)
    trans.process_transcription(force)


@celery.task
def task_parse_video_transcriptions(video_id: int, force: bool = False):
    video = get_video(video_id)
    video.process_transcriptions(force)
    return video_id


@app.route("/transcription/<int:transcription_id>/parse")
@login_required
def parse_transcription(transcription_id: int):
    _ = task_parse_transcription.delay(transcription_id, force=True)
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
def channel_parse_transcriptions(channel_id: int, force: bool = False):
    if current_user.has_permission(PermissionType.Admin):
        channel = get_channel(channel_id)
        for video in channel.videos:
            _ = task_parse_video_transcriptions.delay(video.id, force)
    return redirect(request.referrer)


@app.route("/channel/<int:channel_id>/fetch_audio")
@login_required
def channel_fetch_audio(channel_id: int):
    if current_user.has_permission(PermissionType.Admin):
        channel = get_channel(channel_id)
        for video in channel.videos:
            _ = task_fetch_audio.delay(video.id)
    return redirect(request.referrer)


@app.route("/channel/<int:channel_id>/transcribe_audio")
@login_required
def channel_transcribe_audio(channel_id: int):
    if current_user.has_permission(PermissionType.Admin):
        channel = get_channel(channel_id)
        logger.info(f"Bulk queue audio processing for channel {channel.id}")
        for video in channel.videos:
            if video.audio is not None:
                logger.info(f"Task queued, processing audio for video {video.id}")
                _ = task_transcribe_audio.delay(video.id)
    return redirect(request.referrer)

if __name__ == "__main__":
    app.run(debug=config.debug, host=config.app_host, port=config.app_port)

@app.route("/video/<int:video_id>/upload_transcription", methods=["POST"])
@require_api_key
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