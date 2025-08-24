from flask import Blueprint, render_template, redirect, request, url_for, abort, jsonify
from app.permissions import require_permission, require_api_key
from app.logger import logger
from app.models import db
from app.models import PermissionType, ChatLog
from flask_login import login_required, current_user  # type: ignore
from app.cache import cache, make_cache_key
from app.rate_limit import limiter, rate_limit_exempt
from datetime import timedelta
from io import BytesIO
from flask import send_file
import mimetypes
from app.services import VideoService, UserService
from app.models.config import config

video_blueprint = Blueprint('video', __name__, url_prefix='/video',
                            template_folder='templates', static_folder='static')


@video_blueprint.route("/<int:video_id>/fecth_details")
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def video_fetch_details(video_id: int):
    logger.info("Fetching details for video", extra={"video_id": video_id})
    video = VideoService.get_by_id(video_id)
    VideoService.fetch_details(video)
    return redirect(request.referrer)


@video_blueprint.route("/<int:video_id>/fetch_transcriptions")
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def video_fetch_transcriptions(video_id: int):
    logger.info("Fetching transcriptions for video",
                extra={"video_id": video_id})
    video = VideoService.get_by_id(video_id)
    VideoService.download_transcription(video)
    return redirect(request.referrer)


@video_blueprint.route("/<int:video_id>/archive")
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def video_archive(video_id: int):
    return "Not implemented", 501
    # logger.info("Archiving video", extra={"video_id": video_id})
    # video = VideoService.get_by_id(video_id)
    # video.archive()
    # return redirect(request.referrer)


@video_blueprint.route("/<int:video_id>/delete")
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def video_delete(video_id: int):
    if current_user.is_anonymous == False and UserService.has_permission(current_user, [PermissionType.Admin, PermissionType.Moderator]):
        logger.warning("Deleting video", extra={"video_id": video_id})
        video = VideoService.get_by_id(video_id)
        channel_id = video.channel_id
        VideoService.delete_video(video)
        return redirect(url_for("channel_get_videos", channel_id=channel_id))
    else:
        return "You do not have access", 403


@video_blueprint.route("/<int:video_id>/edit")
@login_required
@limiter.shared_limit("1000 per day, 60 per minute", exempt_when=rate_limit_exempt, scope="normal")
@require_permission()
@cache.cached(timeout=10, make_cache_key=make_cache_key)
def video_edit(video_id: int):
    video = VideoService.get_by_id(video_id)
    return render_template(
        "video.html",
        transcriptions=video.transcriptions,
        video=video,
    )


@video_blueprint.route("/<int:video_id>/chatlogs", methods=["POST", "GET"])
@login_required
@limiter.shared_limit("1000 per day, 60 per minute", exempt_when=rate_limit_exempt, scope="normal")
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def video_chatlogs(video_id: int):
    logger.info("Getting chatlogs for video", extra={"video_id": video_id})
    video = VideoService.get_by_id(video_id)
    start_time = video.uploaded
    end_time = video.uploaded + timedelta(seconds=video.duration)

    if request.method == "POST":
        search = request.form.get("chatSearchInput")
        user_filter = request.form.get("userFilter")
        logger.info("chat search: %s, user filter: %s", search,
                    user_filter, extra={"video_id": video_id})

        if search:
            chat_logs = db.session.query(ChatLog).filter(
                ChatLog.channel_id == video.channel_id,
                ChatLog.timestamp >= start_time,
                ChatLog.timestamp <= end_time,
                ChatLog.message.contains(search)
            ).order_by(ChatLog.timestamp).all()
        else:
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
    else:
        chat_logs = db.session.query(ChatLog).filter(
            ChatLog.channel_id == video.channel_id,
            ChatLog.timestamp >= start_time,
            ChatLog.timestamp <= end_time
        ).order_by(ChatLog.timestamp).all()
        
        formatted_logs = [{
            "id": log.id,
            "username": log.username,
            "message": log.message,
            "timestamp": log.timestamp.isoformat(),
            "offset_seconds": (log.timestamp - start_time).total_seconds()
        } for log in chat_logs]
        
        response = jsonify({
            "video_platform_ref": video.platform_ref,
            "video_platform_type": video.channel.platform_name,
            "chat_logs": formatted_logs
        })
        
        response.cache_control.max_age = config.default_cache_time
        response.cache_control.must_revalidate = True
        response.cache_control.public = True
        
        return response




@video_blueprint.route("/<int:video_id>/parse_transcriptions")
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def parse_transcriptions(video_id: int):
    logger.info("Requesting transcriptions to be parsed",
                extra={"video_id": video_id})
    video = VideoService.get_by_id(video_id)
    VideoService.process_transcriptions(video, force=True)
    return redirect(request.referrer)


@video_blueprint.route("/<int:video_id>/debug_audio")
@login_required
@require_permission(permissions=[PermissionType.Admin])
def serve_debug_audio(video_id: int):
    try:
        video = VideoService.get_by_id(video_id)
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
        video = VideoService.get_by_id(video_id)
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


@video_blueprint.route("/<int:video_id>/transcription_segments")
@login_required
@limiter.shared_limit("1000 per day, 60 per minute", exempt_when=rate_limit_exempt, scope="normal")
@require_permission()
def video_transcription_segments(video_id: int):
    """Return transcription segments as JSON for searchable table"""
    logger.info("Getting transcription segments for video", extra={"video_id": video_id})
    video = VideoService.get_by_id(video_id)
    
    if not video:
        abort(404, description="Video not found")
    
    segments = []
    for transcription in video.transcriptions:
        if transcription.processed:
            for segment in transcription.segments:
                segments.append({
                    "id": segment.id,
                    "transcription_id": transcription.id,
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text,
                    "timestamp_url": f"{VideoService.get_url(video)}{'&' if '?' in VideoService.get_url(video) else '?'}t={int(segment.start)}s"
                })
    
    # Sort by start time
    segments.sort(key=lambda x: float(x["start"])) # type: ignore
    
    response = jsonify({
        "video_platform_ref": video.platform_ref,
        "video_platform_type": video.channel.platform_name,
        "segments": segments
    })
    
    response.cache_control.max_age = config.default_cache_time
    response.cache_control.must_revalidate = True
    response.cache_control.public = True
    
    return response
