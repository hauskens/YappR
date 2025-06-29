from flask import Blueprint, render_template, redirect, request, url_for, abort
from app.permissions import require_permission, require_api_key
from app.logger import logger
from app.models.db import PermissionType
from flask_login import login_required, current_user # type: ignore
from app.retrievers import get_video
from app.cache import cache, make_cache_key
from app.rate_limit import limiter, rate_limit_exempt
from app.models.db import db, ChatLog
from datetime import timedelta
from io import BytesIO
from flask import send_file
import mimetypes

video_blueprint = Blueprint('video', __name__, url_prefix='/video', template_folder='templates', static_folder='static')

@video_blueprint.route("/<int:video_id>/fecth_details")
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def video_fetch_details(video_id: int):
    logger.info("Fetching details for video", extra={"video_id": video_id})
    video = get_video(video_id)
    video.fetch_details()
    return redirect(request.referrer)


@video_blueprint.route("/<int:video_id>/fetch_transcriptions")
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def video_fetch_transcriptions(video_id: int):
    logger.info("Fetching transcriptions for video", extra={"video_id": video_id})
    video = get_video(video_id)
    video.download_transcription(force=True)
    return redirect(request.referrer)


@video_blueprint.route("/<int:video_id>/archive")
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def video_archive(video_id: int):
    logger.info("Archiving video", extra={"video_id": video_id})
    video = get_video(video_id)
    video.archive()
    return redirect(request.referrer)

@video_blueprint.route("/<int:video_id>/delete")
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def video_delete(video_id: int):
    if current_user.is_anonymous == False and current_user.has_permission(PermissionType.Admin):
        logger.warning("Deleting video", extra={"video_id": video_id})
        video = get_video(video_id)
        channel_id = video.channel_id
        video.delete()
        return redirect(url_for("channel_get_videos", channel_id=channel_id))
    else:
        return "You do not have access", 403

@video_blueprint.route("/<int:video_id>/edit")
@login_required
@limiter.shared_limit("1000 per day, 60 per minute", exempt_when=rate_limit_exempt, scope="normal")
@cache.cached(timeout=10, make_cache_key=make_cache_key)
def video_edit(video_id: int):
    video = get_video(video_id)
    return render_template(
        "video_edit.html",
        transcriptions=video.transcriptions,
        video=video,
    )

@video_blueprint.route("/<int:video_id>/chatlogs")
@login_required
@limiter.shared_limit("1000 per day, 60 per minute", exempt_when=rate_limit_exempt, scope="normal")
@cache.cached(timeout=600)
def video_chatlogs(video_id: int):
    logger.info("Getting chatlogs for video", extra={"video_id": video_id})
    video = get_video(video_id)
    
    # Get chat messages from the channel during the video timeframe
    start_time = video.uploaded
    end_time = video.uploaded + timedelta(seconds=video.duration)
    
    chat_logs = db.session.query(ChatLog).filter(
        ChatLog.channel_id == video.channel_id,
        ChatLog.timestamp >= start_time,
        ChatLog.timestamp <= end_time
    ).order_by(ChatLog.timestamp).all()
    
    return render_template(
        "video_chatlogs.html",
        chat_logs=chat_logs,
        video=video
    )


@video_blueprint.route("/<int:video_id>/parse_transcriptions")
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def parse_transcriptions(video_id: int):
    logger.info("Requesting transcriptions to be parsed", extra={"video_id": video_id})
    video = get_video(video_id)
    video.process_transcriptions(force=True)
    return redirect(request.referrer)

@video_blueprint.route("/<int:video_id>/debug_audio")
@login_required
@require_permission(permissions=[PermissionType.Admin])
def serve_debug_audio(video_id: int):
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

@video_blueprint.route("/<int:video_id>/download_audio")
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