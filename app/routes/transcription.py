from flask import Blueprint, redirect, request, abort
from flask_login import current_user, login_required  # type: ignore
from app.permissions import require_permission
from app.models.transcription import Transcription
from app.models import db
from app.models.enums import PermissionType
from app.retrievers import get_transcription
from io import BytesIO
from flask import send_file
from app.logger import logger

transcription_blueprint = Blueprint(
    'transcription', __name__, url_prefix='/transcription', template_folder='templates', static_folder='static')


@transcription_blueprint.route("/<int:transcription_id>/download")
@login_required
@require_permission()
def download_transcription(transcription_id: int):
    transcription = get_transcription(transcription_id)
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
    transcription = get_transcription(transcription_id)
    srt_content = transcription.to_srt()
    return send_file(
        BytesIO(srt_content.encode('utf-8')),
        mimetype="text/plain",
        download_name=f"{transcription.id}.srt",
    )


@transcription_blueprint.route("/<int:transcription_id>/download_json")
@login_required
@require_permission()
def download_transcription_json(transcription_id: int):
    transcription = get_transcription(transcription_id)
    json_content = transcription.to_json()
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
    transcription = get_transcription(transcription_id)
    transcription.reset()
    return redirect(request.referrer)


@transcription_blueprint.route("/<int:transcription_id>/delete")
@login_required
@require_permission()
def delete_transcription(transcription_id: int):
    transcription = get_transcription(transcription_id)
    broadcaster_id = transcription.video.channel.broadcaster_id

    # Custom permission check since we need to check multiple conditions
    if current_user.has_permission([PermissionType.Admin, PermissionType.Moderator]) or current_user.has_broadcaster_id(broadcaster_id):
        logger.info("Deleting transcription", extra={
                    "transcription_id": transcription_id, "video_id": transcription.video_id, "user_id": current_user.id})
        transcription.delete()
        db.session.commit()
        return redirect(request.referrer)
    else:
        logger.error("User does not have permission to delete transcription", extra={
                     "transcription_id": transcription_id, "video_id": transcription.video_id, "user_id": current_user.id})
        return abort(403)
