import redis
import requests
import os
import json
import tempfile
from .models.utils import DownloadProgress
import mimetypes
import asyncio
from flask_login import current_user, login_required  # type: ignore
from flask import (
    Flask,
    render_template,
    request,
    redirect,
)
from celery import Celery, Task, chain
from celery.result import AsyncResult
from app.models import db
from app.models import Transcription, TranscriptionSource, TranscriptionResult, PermissionType
from app.transcribe import transcribe
from app.models.config import config
from app.services import ChannelService, VideoService, TranscriptionService, UserService
from app import app, login_manager, socketio
from app.csrf import csrf
from app.permissions import require_api_key, require_permission
from app.twitch_api import get_current_live_streams
from urllib.parse import unquote
from celery.schedules import crontab
from app.chatlogparse import parse_logs
from flask_socketio import emit, send
from app.logger import logger
from flask_socketio import emit, join_room, leave_room, send
from datetime import datetime, timedelta
import uuid
from werkzeug.utils import secure_filename


def celery_init_app(app: Flask) -> Celery:
    class FlaskTask(Task):
        def __call__(self, *args: object, **kwargs: object) -> object:
            with app.app_context():
                return self.run(*args, **kwargs)  # type: ignore

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
        channels = ChannelService.get_all(show_hidden=True)
        for channel in channels:
            # TODO: add channel setting for this
            if str(channel.platform_name).lower() == "twitch":
                logger.info("Setting up tasks for channel",
                            extra={"channel_id": channel.id})
                sender.add_periodic_task(crontab(hour="*", minute="*/15"), full_processing_task.s(
                    channel.id), name=f'look for new videos every 15 minutes - {channel.name}')
        sender.add_periodic_task(crontab(hour="*", minute="*/5"), update_channels_last_active.s(
        ), name=f'update channels last active every 5 minutes')


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
    channel = ChannelService.get_by_id(channel_id)
    if channel.last_active is not None and channel.last_active > datetime.now() - timedelta(minutes=30):
        logger.info("Channel was active less than 30 minutes ago, skipping", extra={
                    "channel_id": channel_id})
        return
    logger.info("Channel was active more than 30 minutes ago, processing", extra={
                "channel_id": channel_id})
    
    # Get last 5 existing videos from channel, ordered by upload date
    recent_videos = ChannelService.get_videos_by_channel(channel_id)[:5]
    
    unprocessed_count = 0
    for video in recent_videos:
        # Check if video has transcription from system (TranscriptionSource.Unknown)
        has_system_transcription = any(
            t.source == TranscriptionSource.Unknown 
            for t in video.transcriptions
        )
        
        if not has_system_transcription:
            logger.info("Starting full processing for unprocessed video", 
                       extra={"video_id": video.id, "channel_id": channel_id})
            _ = chain(
                task_fetch_audio.s(video.id),
                task_transcribe_audio.s(),
                task_parse_video_transcriptions.s(),
            ).apply_async(ignore_result=True)
            unprocessed_count += 1
    
    logger.info("Full processing task completed", extra={
        "channel_id": channel_id,
        "total_videos_checked": len(recent_videos),
        "unprocessed_videos_queued": unprocessed_count
    })


@app.route("/<int:channel_id>/parse_logs/<folder_path>")
@login_required
@require_permission([PermissionType.Admin, PermissionType.Moderator])
def parse_logs_route(channel_id: int, folder_path: str):
    with app.app_context():
        parse_logs(
            f'/chatterino_logs/Twitch/Channels/{folder_path}', channel_id)
    return "Done"


@app.route("/video/<int:video_id>/process_audio")
@login_required
@require_permission([PermissionType.Admin, PermissionType.Moderator])
def video_process_audio(video_id: int):
    logger.info("Processing audio for", extra={"video_id": video_id})
    _ = task_transcribe_audio.delay(video_id)
    return redirect(request.referrer)


@app.route("/video/<int:video_id>/process_full")
@login_required
@require_permission([PermissionType.Admin, PermissionType.Moderator])
def video_process_full(video_id: int):
    logger.info("Full processing of video", extra={"video_id": video_id})
    _ = chain(
        task_fetch_audio.s(video_id),
        task_transcribe_audio.s(),
        task_parse_video_transcriptions.s(),
    ).apply_async(ignore_result=True)
    return redirect(request.referrer)


@app.route("/video/<int:video_id>/fecth_audio")
@login_required
@require_permission([PermissionType.Admin, PermissionType.Moderator])
def video_fetch_audio(video_id: int):
    logger.info("Fetching audio for", extra={"video_id": video_id})
    _ = chain(task_fetch_audio.s(video_id), task_transcribe_audio.s(),
              task_parse_video_transcriptions.s()).apply_async(ignore_result=True)

    return redirect(request.referrer)


@app.route("/celery/active-view")
@login_required
@require_permission([PermissionType.Admin, PermissionType.Moderator])
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


@app.route("/celery/task-status/<task_id>")
@login_required
@require_permission([PermissionType.Admin, PermissionType.Moderator])
def get_task_status_html(task_id: str):
    from .models.utils import DownloadProgress
    from app.transcribe import transcription_tracker
    
    result: AsyncResult = AsyncResult(task_id, app=celery)

    if result.state == 'PROGRESS':
        # Check if result.result is a dictionary before unpacking
        if isinstance(result.result, dict):
            meta: DownloadProgress = DownloadProgress(**result.result)
            percent = meta.percent
            status = meta.status
            speed = meta.speed
            eta = meta.eta
            
            speed_str = f"{speed/1024/1024:.1f} MB/s" if speed > 0 else ""
            eta_str = f"{eta:.2f}s" if eta is not None and eta > 0 else ""

            return f'''
            <div class="progress mb-2">
                <div class="progress-bar" role="progressbar" 
                     style="width: {percent}%" 
                     aria-valuenow="{percent}" 
                     aria-valuemin="0" 
                     aria-valuemax="100">
                    {percent}%
                </div>
            </div>
            <div class="small text-muted">
                {status}{f" • {speed_str}" if speed_str else ""}{f" • ETA: {eta_str}" if eta_str else ""}
            </div>
            <div hx-get="/celery/task-status/{task_id}" 
                 hx-trigger="every 2s" 
                 hx-target="closest .progress-status"
                 hx-swap="innerHTML">
            </div>
            '''
        else:
            # Handle the case where result.result is not a dictionary
            return '<div class="text-warning">⚠️ Task in progress but invalid progress data, it probably works fine, it just doesn\'t show progress</div>'
    elif result.state == 'SUCCESS':
        return '<div class="text-success">✓ Completed</div>'
    elif result.state == 'FAILURE':
        return '<div class="text-danger">✗ Failed</div>'
    elif result.state == 'STARTED':
        # Check if this is a transcription task with progress tracking
        progress_data = transcription_tracker.get_progress_estimate(task_id)
        if progress_data:
            percent = progress_data['percent']
            status = progress_data['status']
            eta = progress_data['eta']
            
            eta_str = f"{eta:.2f}s" if eta > 0 else ""
            
            return f'''
            <div class="progress mb-2">
                <div class="progress-bar" role="progressbar" 
                     style="width: {percent}%" 
                     aria-valuenow="{percent}" 
                     aria-valuemin="0" 
                     aria-valuemax="100">
                    {percent}%
                </div>
            </div>
            <div class="small text-muted">
                {status}{f" • ETA: {eta_str}" if eta_str else ""}
            </div>
            <div hx-get="/celery/task-status/{task_id}" 
                 hx-trigger="every 2s" 
                 hx-target="closest .progress-status"
                 hx-swap="innerHTML">
            </div>
            '''
        else:
            return f'''
            <div class="text-info">
                <i class="bi bi-play-circle"></i> Task started...
            </div>
            <div hx-get="/celery/task-status/{task_id}" 
                 hx-trigger="every 2s" 
                 hx-target="closest .progress-status"
                 hx-swap="innerHTML">
            </div>
            '''
    else:
        # Check if this is a transcription task with progress tracking (for PENDING state)
        progress_data = transcription_tracker.get_progress_estimate(task_id)
        if progress_data:
            percent = progress_data['percent']
            status = progress_data['status']
            eta = progress_data['eta']
            
            eta_str = f"{eta:.2f}s" if eta > 0 else ""
            
            return f'''
            <div class="progress mb-2">
                <div class="progress-bar" role="progressbar" 
                     style="width: {percent}%" 
                     aria-valuenow="{percent}" 
                     aria-valuemin="0" 
                     aria-valuemax="100">
                    {percent}%
                </div>
            </div>
            <div class="small text-muted">
                {status}{f" • ETA: {eta_str}" if eta_str else ""}
            </div>
            <div hx-get="/celery/task-status/{task_id}" 
                 hx-trigger="every 2s" 
                 hx-target="closest .progress-status"
                 hx-swap="innerHTML">
            </div>
            '''
        else:
            return f'''
            <div class="text-muted">
                <i class="bi bi-clock"></i> Working...
            </div>
            <div hx-get="/celery/task-status/{task_id}" 
                 hx-trigger="every 2s" 
                 hx-target="closest .progress-status"
                 hx-swap="innerHTML">
            </div>
            '''


@celery.task(bind=True, name='app.main.task_fetch_audio')
def task_fetch_audio(self, video_id: int):
    logger.info("Fetching audio for", extra={"video_id": video_id})
    video = VideoService.get_by_id(video_id)

    # Create a progress callback for yt-dlp
    def progress_hook(d):
        if d['status'] == 'downloading':
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            if total > 0:
                percent = int((downloaded / total) * 100)
                speed = d.get('speed', 0)
                eta = d.get('eta')

                # Create a DownloadProgress object and use it to update Celery task state
                progress = DownloadProgress(
                    current=downloaded,
                    total=total,
                    percent=percent,
                    speed=speed,
                    eta=eta,
                    status=f'Downloading audio... {percent}%'
                )

                # Update Celery task state
                self.update_state(
                    state='PROGRESS',
                    meta=progress.dict()
                )

    VideoService.save_audio(video, progress_callback=progress_hook)
    return video_id


@celery.task()
def task_fetch_transcription(video_id: int):
    video = VideoService.get_by_id(video_id)
    logger.info("Task queued, fetching transcription for",
                extra={"video_id": video_id})
    _ = VideoService.download_transcription(video)
    return video_id


@celery.task
def update_channels_last_active():
    channels = ChannelService.get_all_twitch_channels()
    twitch_user_ids = [channel.platform_channel_id for channel in channels]
    logger.info("Updating channels last active")
    if len(twitch_user_ids) > 0:
        streams = asyncio.run(get_current_live_streams(twitch_user_ids))
        for stream in streams:
            for channel in channels:
                if channel.platform_channel_id == stream.user_id:
                    channel.last_active = datetime.now()
    db.session.commit()


@celery.task(bind=True, name='app.main.task_transcribe_audio')
def task_transcribe_audio(self, video_id: int, force: bool = False):
    from app.transcribe import transcription_tracker
    import time
    
    headers = {"X-API-Key": config.api_key}
    video = VideoService.get_by_id(video_id)

    for t in video.transcriptions:
        if t.source == TranscriptionSource.Unknown:
            if not force:
                logger.info("Transcription already exists on video",
                            extra={"video_id": video_id})
                return video_id
            logger.info("Transcription already exists on video",
                        extra={"video_id": video_id})
            TranscriptionService.delete(t)

    logger.info("Task queued, processing audio for video",
                extra={"video_id": video_id})

    if not video.audio:
        logger.warning("No audio associated with video",
                       extra={"video_id": video_id})
        return video_id

    # Start progress tracking with video duration
    transcription_tracker.start_progress_tracking(self.request.id, video.duration)
    transcription_start_time = time.time()

    download_url = f"{config.app_url}/video/{video.id}/download_audio"

    try:
        with requests.get(download_url, headers=headers, stream=True) as r:
            r.raise_for_status()
            ext = get_extension_from_response(r)
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext, dir=config.cache_location) as temp_file:
                for chunk in r.iter_content(chunk_size=8192):
                    temp_file.write(chunk)
                local_filename = temp_file.name

        logger.info(f"Audio downloaded to %s, starting transcription",
                    local_filename, extra={"video_id": video_id})

        result_file = transcribe(local_filename)
        
        # Calculate transcription time and store metrics
        transcription_end_time = time.time()
        transcription_time = transcription_end_time - transcription_start_time
        transcription_tracker.store_completion_metrics(video.duration, transcription_time)

        with open(result_file, "r") as f:
            result = json.load(f)

        logger.info("Uploading transcription to video",
                    extra={"video_id": video_id})
        upload_url = f"{config.app_url}/video/{video_id}/upload_transcription"
        headers.update(
            {"Content-type": "application/json", "Accept": "text/plain"})
        response = requests.post(upload_url, json=result, headers=headers)
        response.raise_for_status()

    except Exception as e:
        logger.error("Transcription task failed: %s", e,
                     exc_info=True, extra={"video_id": video_id})
        raise

    finally:
        # Clean up temp file and progress tracking
        try:
            if os.path.exists(local_filename):
                os.remove(local_filename)
        except Exception as cleanup_error:
            logger.warning("Failed to delete temp file %s",
                           cleanup_error, extra={"video_id": video_id})
        
        # Cleanup progress tracking
        transcription_tracker.cleanup_progress_tracking(self.request.id)

    return video_id


@app.route("/utils/upload_audio", methods=["POST"])
@login_required
@require_permission([PermissionType.Admin, PermissionType.Moderator])
def upload_audio():

    logger.info("Uploading audio file")
    try:
        if "audio_file" not in request.files:
            return "<div class='alert alert-danger'>No file part</div>", 400

        file = request.files["audio_file"]
        if file.filename == "":
            return "<div class='alert alert-danger'>No selected file</div>", 400

        # Generate a unique filename
        original_filename = secure_filename(file.filename)
        file_ext = os.path.splitext(original_filename)[1].lower()

        # Check if extension is allowed
        allowed_extensions = {".mp3", ".wav", ".ogg", ".m4a", ".flac"}
        if file_ext not in allowed_extensions:
            return f"<div class='alert alert-danger'>File type not allowed. Allowed types: {', '.join(allowed_extensions)}</div>", 400

        # Create a unique ID for this job
        job_id = str(uuid.uuid4())

        # Create cache directory if it doesn't exist
        cache_dir = os.path.abspath(os.path.join(
            config.cache_location, "transcription_jobs"))
        os.makedirs(cache_dir, exist_ok=True)

        # Save the file
        filename = f"{job_id}{file_ext}"
        filepath = os.path.join(cache_dir, filename)
        file.save(filepath)

        # Create a metadata file
        metadata = {
            "job_id": job_id,
            "original_filename": original_filename,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "user_id": current_user.id,
            "username": current_user.name
        }

        metadata_path = os.path.join(cache_dir, f"{job_id}.json")
        with open(metadata_path, "w") as f:
            json.dump(metadata, f)

        # Queue the transcription task
        task = task_transcribe_file.delay(job_id)

        logger.info(f"Queued transcription job {job_id}")

        return f"""
        <div class="alert alert-success">
            <h5>File uploaded successfully!</h5>
            <p>Your file has been queued for transcription.</p>
            <p><strong>Job ID:</strong> {job_id}</p>
        </div>
        """

    except Exception as e:
        logger.error(f"Error uploading file: {e}", exc_info=True)
        return f"<div class='alert alert-danger'>Error uploading file: {str(e)}</div>", 500


@celery.task
def task_transcribe_file(job_id: str):
    logger.info("Task queued, processing audio file", extra={"job_id": job_id})

    # Get the cache directory
    cache_dir = os.path.join(config.cache_location, "transcription_jobs")
    metadata_path = os.path.join(cache_dir, f"{job_id}.json")

    download_url = f"{config.app_url}/utils/download_audio/{job_id}"
    headers = {"X-API-Key": config.api_key}
    with requests.get(download_url, headers=headers, stream=True) as r:
        r.raise_for_status()
        ext = get_extension_from_response(r)
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext, dir=config.cache_location) as temp_file:
            for chunk in r.iter_content(chunk_size=8192):
                temp_file.write(chunk)
                local_filename = temp_file.name

    logger.info(f"Audio downloaded to %s, starting transcription",
                local_filename, extra={"job_id": job_id})

    result_file = transcribe(local_filename)

    with open(result_file, "r") as f:
        result = json.load(f)

    logger.info("Uploading transcription to video", extra={"job_id": job_id})
    upload_url = f"{config.app_url}/utils/upload_transcription/{job_id}"
    headers.update(
        {"Content-type": "application/json", "Accept": "text/plain"})
    response = requests.post(upload_url, json=result, headers=headers)
    response.raise_for_status()

    return job_id


@celery.task
def task_parse_transcription(transcription_id: int, force: bool = False):
    trans = TranscriptionService.get_by_id(transcription_id)
    TranscriptionService.process_transcription(trans, force)


@celery.task
def task_parse_video_transcriptions(video_id: int, force: bool = False):
    video = VideoService.get_by_id(video_id)
    VideoService.process_transcriptions(video, force)
    return video_id


@celery.task(name='app.task_download_twitch_clip')
def task_download_twitch_clip(video_url: str, start_time: int, duration: int):
    from app.tasks import get_twitch_segment
    logger.info("Downloading Twitch clip for %s from %s for %s seconds",
                video_url, start_time, duration)
    try:
        clip_basename = get_twitch_segment(video_url, start_time, duration)
        logger.info("Twitch clip downloaded successfully: %s", clip_basename)
        return clip_basename
    except Exception as e:
        logger.error("Failed to download Twitch clip: %s", e, exc_info=True)
        raise


@app.route("/transcription/<int:transcription_id>/parse")
@login_required
def parse_transcription(transcription_id: int):
    _ = task_parse_transcription.delay(transcription_id, force=True)
    return redirect(request.referrer)


# todo: send some confirmation to user that task is queued and prevent new queue from getting started
@app.route("/channel/<int:channel_id>/fetch_transcriptions")
@login_required
def channel_fetch_transcriptions(channel_id: int):
    if current_user.is_anonymous == False and UserService.has_permission(current_user, PermissionType.Admin):
        channel = ChannelService.get_by_id(channel_id)
        logger.info("Fetching all transcriptions for channel",
                    extra={"channel_id": channel_id})
        for video in channel.videos:
            _ = task_fetch_transcription.delay(video.id)
    return redirect(request.referrer)


@app.route("/channel/<int:channel_id>/parse_transcriptions")
@login_required
def channel_parse_transcriptions(channel_id: int, force: bool = False):
    if current_user.is_anonymous == False and UserService.has_permission(current_user, PermissionType.Admin):
        channel = ChannelService.get_by_id(channel_id)
        for video in channel.videos:
            _ = task_parse_video_transcriptions.delay(video.id, force)
    return redirect(request.referrer)


@app.route("/channel/<int:channel_id>/fetch_audio")
@login_required
def channel_fetch_audio(channel_id: int):
    if current_user.is_anonymous == False and UserService.has_permission(current_user, PermissionType.Admin):
        channel = ChannelService.get_by_id(channel_id)
        for video in channel.videos:
            _ = task_fetch_audio.delay(video.id)
    return redirect(request.referrer)


@app.route("/channel/<int:channel_id>/transcribe_audio")
@login_required
def channel_transcribe_audio(channel_id: int):
    if current_user.is_anonymous == False and UserService.has_permission(current_user, PermissionType.Admin):
        channel = ChannelService.get_by_id(channel_id)
        logger.info("Bulk queue audio processing for channel",
                    extra={"channel_id": channel_id})
        for video in channel.videos:
            if video.audio is not None:
                logger.info("Task queued, processing audio for video",
                            extra={"video_id": video.id})
                _ = task_transcribe_audio.delay(video.id)
    return redirect(request.referrer)


@app.route("/video/<int:video_id>/download_clip", methods=["POST"])
@login_required
@require_permission([PermissionType.Admin, PermissionType.Moderator])
def download_clip(video_id: int):
    start_time = request.form.get("start_time", type=int)
    before_seconds = request.form.get("before_seconds", type=int, default=30)
    after_seconds = request.form.get("after_seconds", type=int, default=30)

    if start_time is None:
        return '<div class="alert alert-danger">Start time required</div>', 400

    # Validate timeshift parameters
    before_seconds = max(0, min(150, before_seconds))  # 0-150 seconds
    after_seconds = max(0, min(150, after_seconds))    # 0-150 seconds
    total_duration = before_seconds + after_seconds

    if total_duration > 180:  # Max 3 minutes total
        return '<div class="alert alert-danger">Total clip duration cannot exceed 3 minutes (180 seconds)</div>', 400

    if total_duration == 0:
        return '<div class="alert alert-danger">Clip duration must be at least 1 second</div>', 400

    video = VideoService.get_by_id(video_id)
    if "twitch" not in VideoService.get_url(video).lower():
        return '<div class="alert alert-danger">Only Twitch videos supported</div>', 400

    # Calculate clip start and duration
    clip_start = max(0, start_time - before_seconds)
    duration = total_duration

    # Generate the expected clip basename
    video_id_from_url = VideoService.get_url(video).split('/')[-1]
    clip_basename = f"{video_id_from_url}_{clip_start}_{duration}_clip"

    logger.info("Queuing clip download for video %s from %s for %s seconds (-%ss/+%ss)",
                video_id, clip_start, duration, before_seconds, after_seconds)
    task = task_download_twitch_clip.delay(
        VideoService.get_url(video), clip_start, duration)

    # Return HTML with polling for status updates using file-based checking
    return f'''
    <div class="clip-status">
        <span class="text-muted">
            <span class="spinner-border spinner-border-sm me-1" role="status"></span>
            Processing {duration}s clip...
        </span>
        <div hx-get="/clip/{clip_basename}/status_html" 
             hx-trigger="every 2s" 
             hx-target="closest .clip-status"
             hx-swap="outerHTML">
        </div>
    </div>
    ''', 200


def check_clip_file_status(clip_basename: str):
    """Check for clip files by basename pattern"""
    import glob

    # Use the same directory logic as tasks.py
    storage_directory = os.path.abspath(config.cache_location)
    clips_directory = os.path.join(storage_directory, "clips")
    logger.debug("Checking for clip files with basename: %s in directory: %s",
                 clip_basename, clips_directory)
    logger.debug("Config cache_location: %s, storage_directory: %s",
                 config.cache_location, storage_directory)

    # Look for ALL files matching the basename pattern
    all_pattern = os.path.join(clips_directory, f"{clip_basename}*")
    all_files = glob.glob(all_pattern)
    logger.debug("Found files matching pattern %s: %s", all_pattern, all_files)

    if not all_files:
        logger.debug("No files found, returning PENDING")
        return {
            'state': 'PENDING',
            'status': 'Queued...'
        }

    # Look for fragment/temp files (indicates download in progress)
    fragment_extensions = ['.f0', '.f1', '.f2', '.f3', '.f4', '.f5', '.f6', '.f7', '.f8', '.f9',
                           '.part', '.ytdl', '.tmp', '.download']
    temp_files = [f for f in all_files if any(
        f.lower().endswith(ext) for ext in fragment_extensions)]

    if temp_files:
        logger.debug("Found temp/fragment files: %s", temp_files)
        return {
            'state': 'PROGRESS',
            'status': 'Downloading...'
        }

    # Look for completed video files (any extension that's not a temp file)
    video_extensions = ['.mp4', '.mkv', '.webm',
                        '.avi', '.mov', '.flv', '.m4v', '.ts', '.m4a']
    completed_files = [f for f in all_files if any(
        f.lower().endswith(ext) for ext in video_extensions)]

    if completed_files:
        # File is complete
        filename = os.path.basename(completed_files[0])
        logger.debug("Found completed file: %s", filename)
        return {
            'state': 'SUCCESS',
            'status': 'Complete',
            'filename': filename,
            'download_url': f"/clips/{filename}"
        }

    # Files exist but no recognizable video format - might be an unknown extension
    # Let's just take the first file and assume it's complete
    filename = os.path.basename(all_files[0])
    logger.debug("Found unknown file type, assuming complete: %s", filename)
    return {
        'state': 'SUCCESS',
        'status': 'Complete',
        'filename': filename,
        'download_url': f"/clips/{filename}"
    }


@app.route("/clip/<clip_basename>/status_html")
@login_required
@require_permission([PermissionType.Admin, PermissionType.Moderator])
def clip_status_html(clip_basename: str):
    result = check_clip_file_status(clip_basename)

    if result['state'] == 'SUCCESS':
        return f'''
        <div class="clip-status mb-2">
            <a href="{result['download_url']}" class="btn btn-sm btn-primary ms-2" download>
                <i class="bi bi-download"></i> Download Clip
            </a>
        </div>
        '''
    elif result['state'] == 'PROGRESS':
        return f'''
        <div class="clip-status">
            <span class="text-muted">
                <span class="spinner-border spinner-border-sm me-1" role="status"></span>
                {result['status']}
            </span>
            <div hx-get="/clip/{clip_basename}/status_html" 
                 hx-trigger="every 2s" 
                 hx-target="closest .clip-status"
                 hx-swap="outerHTML">
            </div>
        </div>
        '''
    else:  # PENDING
        return f'''
        <div class="clip-status">
            <span class="text-muted">
                <span class="spinner-border spinner-border-sm me-1" role="status"></span>
                {result['status']}
            </span>
            <div hx-get="/clip/{clip_basename}/status_html" 
                 hx-trigger="every 2s" 
                 hx-target="closest .clip-status"
                 hx-swap="outerHTML">
            </div>
        </div>
        '''


@app.route("/clips/<path:filename>")
@login_required
@require_permission([PermissionType.Admin, PermissionType.Moderator])
def serve_clip(filename: str):
    from flask import send_from_directory
    # Use the same directory logic as tasks.py
    storage_directory = os.path.abspath(config.cache_location)
    clips_directory = os.path.join(storage_directory, "clips")
    return send_from_directory(clips_directory, filename)


@app.route("/debug/clips")
@login_required
@require_permission([PermissionType.Admin, PermissionType.Moderator])
def debug_clips():
    import glob

    # Use the same directory logic as tasks.py
    storage_directory = os.path.abspath(config.cache_location)
    clips_directory = os.path.join(storage_directory, "clips")

    all_files = glob.glob(os.path.join(clips_directory, "*"))
    file_info = []
    for file_path in all_files:
        filename = os.path.basename(file_path)
        size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        file_info.append(f"{filename} ({size} bytes)")

    return f"""<pre>Config cache_location: {config.cache_location}
Storage directory: {storage_directory}
Clips directory: {clips_directory}
Directory exists: {os.path.exists(clips_directory)}

Files:
{chr(10).join(file_info) if file_info else 'No files found'}
</pre>"""


@app.route("/video/<int:video_id>/upload_transcription", methods=["POST"])
@require_api_key
@csrf.exempt  # type: ignore
def upload_transcription(video_id: int):
    logger.info(f"ready to receive json on {video_id}")
    video = VideoService.get_by_id(video_id)
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
        emit("connect", {"data": f"id: {request.sid} is connected"})
    else:
        logger.warning("client has connected, but is banned")
        return False


@socketio.on_error()        # Handles the default namespace
def error_handler(e):
    logger.error(f'An error occurred: {e}')


@socketio.on("join_queue")
@login_required
def handle_join():
    """Browser tells us which broadcaster it cares about."""
    broadcaster_id = UserService.get_broadcaster(current_user).id
    if broadcaster_id is None:
        logger.warning("User has no broadcaster id",
                       extra={"user_id": current_user.id})
        return
    join_room(f"queue-{broadcaster_id}")
    logger.info("Client has joined queue %s", broadcaster_id,
                extra={"user_id": current_user.id})


@socketio.on('message')
@login_required
def handleMessage(msg):
    if current_user.is_anonymous == False and current_user.banned == False:
        logger.info('Message: ' + msg, extra={"user_id": current_user.id})
        logger.info(current_user.permissions, extra={
                    "user_id": current_user.id})
        send(msg, broadcast=True)
    else:
        logger.warning("User is anonymous or banned")
        return False


@socketio.on("connect")
@login_required
def my_event():
    logger.info("Client has connected", extra={"user_id": current_user.id})


@socketio.on("disconnect")
@login_required
def handle_disconnect(_):
    broadcaster_id = UserService.get_broadcaster(current_user).id
    if broadcaster_id is None:
        logger.warning("User has no broadcaster id",
                       extra={"user_id": current_user.id})
        return
    leave_room(f"queue-{broadcaster_id}")
    logger.info("Client has disconnected %s", broadcaster_id,
                extra={"user_id": current_user.id})


if __name__ == "__main__":
    # socketio.run(app, debug=config.debug, host=config.app_host, port=config.app_port)
    socketio.run(app, allow_unsafe_werkzeug=config.debug,
                 host=config.app_host, port=config.app_port, debug=config.debug)
