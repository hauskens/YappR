from flask import Blueprint, redirect, request, abort
from flask_login import current_user, login_required  # type: ignore
from app.permissions import require_permission
from app.models import PermissionType
from app.services import TranscriptionService, UserService
from io import BytesIO
from flask import send_file
from app.logger import logger

transcription_blueprint = Blueprint(
    'transcription', __name__, url_prefix='/transcription', template_folder='templates', static_folder='static')


@transcription_blueprint.route("/<int:transcription_id>/download")
@login_required
@require_permission()
def download_transcription(transcription_id: int):
    transcription = TranscriptionService.get_by_id(transcription_id)
    content = transcription.file.file.read()
    return send_file(
        BytesIO(content),
        mimetype="text/plain",
        download_name=f"{transcription.id}.{transcription.file_extention}",
    )


@transcription_blueprint.route("/<int:transcription_id>/download_srt")
@login_required
@require_permission()
def download_transcription_srt(transcription_id: int):
    transcription = TranscriptionService.get_by_id(transcription_id)
    srt_content = TranscriptionService.to_srt(transcription)
    return send_file(
        BytesIO(srt_content.encode('utf-8')),
        mimetype="text/plain",
        download_name=f"{transcription.id}.srt",
    )


@transcription_blueprint.route("/<int:transcription_id>/download_json")
@login_required
@require_permission()
def download_transcription_json(transcription_id: int):
    transcription = TranscriptionService.get_by_id(transcription_id)
    json_content = TranscriptionService.to_json(transcription)
    return send_file(
        BytesIO(json_content.encode('utf-8')),
        mimetype="application/json",
        download_name=f"{transcription.id}.json",
    )


@transcription_blueprint.route("/<int:transcription_id>/purge")
@login_required
@require_permission(permissions=PermissionType.Admin)
def purge_transcription(transcription_id: int):
    logger.info("Purging transcription", extra={
                "transcription_id": transcription_id, "user_id": current_user.id})
    transcription = TranscriptionService.get_by_id(transcription_id)
    TranscriptionService.reset_transcription(transcription)
    return redirect(request.referrer)


@transcription_blueprint.route("/<int:transcription_id>/delete")
@login_required
@require_permission()
def delete_transcription(transcription_id: int):
    transcription = TranscriptionService.get_by_id(transcription_id)
    broadcaster_id = transcription.video.channel.broadcaster_id

    # Custom permission check since we need to check multiple conditions
    if UserService.has_permission(current_user, [PermissionType.Admin, PermissionType.Moderator]) or UserService.has_broadcaster_id(current_user, broadcaster_id):
        logger.info("Deleting transcription", extra={
                    "transcription_id": transcription_id, "video_id": transcription.video_id, "user_id": current_user.id})
        TranscriptionService.delete_transcription(transcription_id)
        return redirect(request.referrer)
    else:
        logger.error("User does not have permission to delete transcription", extra={
                     "transcription_id": transcription_id, "video_id": transcription.video_id, "user_id": current_user.id})
        return abort(403)
