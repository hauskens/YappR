from flask_login import current_user, login_required
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    jsonify,
)
import time
import redis
import json
from celery import Celery, Task, group, chain
from .models.db import (
    PermissionType,
    db,
    Channels,
)
import requests
import os
from .transcribe import transcribe
from .models.config import config
from .retrievers import get_transcription, get_video
from app.routes import *
from app import app, login_manager, socketio
from .models.db import TranscriptionSource
from .utils import require_api_key
import tempfile
import mimetypes
import json
from urllib.parse import unquote
from celery.schedules import crontab
from .chatlogparse import parse_logs
from flask_socketio import emit, send
from app.logger import logger

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

logger.info("Service started")

@celery.on_after_configure.connect
def setup_periodic_tasks(sender: Celery, **kwargs):
    logger.info("Setting up periodic tasks")
    with app.app_context():
        channels = db.session.query(Channels).all()
        for channel in channels:
            if channel.platform.name.lower() == "twitch":
                logger.info("Setting up tasks for channel", extra={"channel_id": channel.id})
                sender.add_periodic_task(crontab(hour="*", minute="*/30"), full_processing_task.s(channel.id), name=f'look for new videos every 30 minutes - {channel.name}')
                
def get_extension_from_response(response):
    # Try to extract filename from Content-Disposition header
    cd = response.headers.get("Content-Disposition", "")
    if "filename=" in cd:
        filename = cd.split("filename=")[-1].strip('" ')
        ext = os.path.splitext(unquote(filename))[-1]
        if ext:
            return ext
    # Fallback: use MIME type
    content_type = response.headers.get("Content-Type")
    ext = mimetypes.guess_extension(content_type)
    return ext or ".tmp"

@app.errorhandler(429)
def ratelimit_handler(e):
    return render_template("unauthorized.html", ratelimit_exceeded=e.description)


@login_manager.unauthorized_handler
def redirect_unauthorized():
    return render_template("unauthorized.html")


@celery.task()
def full_processing_task(channel_id: int):
    logger.info("Processing channel", extra={"channel_id": channel_id})
    channel = get_channel(channel_id)
    video = channel.fetch_latest_videos(process=True)
    if video is not None:
        _ = chain(task_fetch_audio.s(video), task_transcribe_audio.s(), task_parse_video_transcriptions.s()).apply_async(ignore_result=True)


@app.route("/<int:channel_id>/parse_logs/<folder_path>")
def parse_logs_route(channel_id: int, folder_path: str):
    with app.app_context():
        parse_logs(f'/chatterino_logs/Twitch/Channels/{folder_path}', channel_id)
    return "Done"

@app.route("/video/<int:video_id>/process_audio")
@login_required
def video_process_audio(video_id: int):
    logger.info("Processing audio for", extra={"video_id": video_id})
    _ = task_transcribe_audio.delay(video_id)
    return redirect(request.referrer)


@app.route("/video/<int:video_id>/process_full")
@login_required
def video_process_full(video_id: int):
    if current_user.is_anonymous == False and current_user.has_permission(PermissionType.Admin) or current_user.has_permission(
        PermissionType.Moderator
    ):
        logger.info("Full processing of video", extra={"video_id": video_id})
        _ = chain(
            task_fetch_audio.s(video_id),
            task_transcribe_audio.s(),
            task_parse_video_transcriptions.s(),
        ).apply_async(ignore_result=True)
        return redirect(request.referrer)
    else:
        return access_denied()


@app.route("/video/<int:video_id>/fecth_audio")
@login_required
def video_fetch_audio(video_id: int):
    logger.info("Fetching audio for", extra={"video_id": video_id})
    _ = chain(task_fetch_audio.s(video_id), task_transcribe_audio.s(), task_parse_video_transcriptions.s()).apply_async(ignore_result=True)

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
    logger.info("Fetching audio for", extra={"video_id": video_id})
    video = get_video(video_id)
    video.save_audio()
    return video_id


@celery.task()
def task_fetch_transcription(video_id: int):
    video = get_video(video_id)
    logger.info("Task queued, fetching transcription for", extra={"video_id": video_id})
    _ = video.download_transcription()
    return video_id


@celery.task
def task_transcribe_audio(video_id: int, force: bool = False):
    headers = {"X-API-Key": config.api_key}
    video = get_video(video_id)

    for t in video.transcriptions:
        if t.source == TranscriptionSource.Unknown:
            if not force:
                logger.info("Transcription already exists on video", extra={"video_id": video_id})
                return video_id
            logger.info("Transcription already exists on video", extra={"video_id": video_id})
            t.delete()

    logger.info("Task queued, processing audio for video", extra={"video_id": video_id})

    if not video.audio:
        logger.warning("No audio associated with video", extra={"video_id": video_id})
        return video_id

    download_url = f"{config.app_url}/video/{video.id}/download_audio"

    try:
        with requests.get(download_url, headers=headers, stream=True) as r:
            r.raise_for_status()
            ext = get_extension_from_response(r)
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext, dir=config.cache_location) as temp_file:
                for chunk in r.iter_content(chunk_size=8192):
                    temp_file.write(chunk)
                local_filename = temp_file.name

        logger.info(f"Audio downloaded to %s, starting transcription", local_filename, extra={"video_id": video_id})

        result_file = transcribe(local_filename)

        with open(result_file, "r") as f:
            result = json.load(f)

        logger.info("Uploading transcription to video", extra={"video_id": video_id})
        upload_url = f"{config.app_url}/video/{video_id}/upload_transcription"
        headers.update({"Content-type": "application/json", "Accept": "text/plain"})
        response = requests.post(upload_url, json=result, headers=headers)
        response.raise_for_status()

    except Exception as e:
        logger.error("Transcription task failed: %s", e, exc_info=True, extra={"video_id": video_id})
        raise

    finally:
        # Clean up temp file
        try:
            if os.path.exists(local_filename):
                os.remove(local_filename)
        except Exception as cleanup_error:
            logger.warning("Failed to delete temp file %s", cleanup_error, extra={"video_id": video_id})

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
    if current_user.is_anonymous == False and current_user.has_permission(PermissionType.Admin):
        channel = get_channel(channel_id)
        logger.info("Fetching all transcriptions for channel", extra={"channel_id": channel_id})
        for video in channel.videos:
            _ = task_fetch_transcription.delay(video.id)
    return redirect(request.referrer)


@app.route("/channel/<int:channel_id>/parse_transcriptions")
@login_required
def channel_parse_transcriptions(channel_id: int, force: bool = False):
    if current_user.is_anonymous == False and current_user.has_permission(PermissionType.Admin):
        channel = get_channel(channel_id)
        for video in channel.videos:
            _ = task_parse_video_transcriptions.delay(video.id, force)
    return redirect(request.referrer)


@app.route("/channel/<int:channel_id>/fetch_audio")
@login_required
def channel_fetch_audio(channel_id: int):
    if current_user.is_anonymous == False and current_user.has_permission(PermissionType.Admin):
        channel = get_channel(channel_id)
        for video in channel.videos:
            _ = task_fetch_audio.delay(video.id)
    return redirect(request.referrer)


@app.route("/channel/<int:channel_id>/transcribe_audio")
@login_required
def channel_transcribe_audio(channel_id: int):
    if current_user.is_anonymous == False and current_user.has_permission(PermissionType.Admin):
        channel = get_channel(channel_id)
        logger.info("Bulk queue audio processing for channel", extra={"channel_id": channel_id})
        for video in channel.videos:
            if video.audio is not None:
                logger.info("Task queued, processing audio for video", extra={"video_id": video.id})
                _ = task_transcribe_audio.delay(video.id)
    return redirect(request.referrer)


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

@socketio.on("connect")
@login_required
def connected():
    """event listener when client connects to the server"""
    if current_user.is_anonymous == False and current_user.banned == False:
        logger.info(request.sid)
        logger.info("client has connected")
        emit("connect",{"data":f"id: {request.sid} is connected"})
    else:
        logger.warning("client has connected, but is banned")
        return False

@socketio.on_error()        # Handles the default namespace
def error_handler(e):
    logger.error(f'An error occurred: {e}')

@socketio.on('message')
@login_required
def handleMessage(msg):
    if current_user.is_anonymous == False and current_user.banned == False:
        logger.info('Message: ' + msg)
        logger.info(current_user.permissions)
        send(msg, broadcast=True)
    else:
        logger.warning("User is anonymous or banned")
        return False


if __name__ == "__main__":
    # socketio.run(app, debug=config.debug, host=config.app_host, port=config.app_port)
    socketio.run(app, allow_unsafe_werkzeug=config.debug, host=config.app_host, port=config.app_port, debug=config.debug)