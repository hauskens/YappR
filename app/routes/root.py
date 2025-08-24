from flask import Blueprint, render_template, flash, send_from_directory, url_for, send_file, make_response, abort, jsonify, request, Response
from app.logger import logger
from flask_login import current_user, logout_user, login_required  # type: ignore
from app.permissions import require_permission, require_api_key, check_banned
from app.models import PermissionType
from app.csrf import csrf
from app.retrievers import (
    get_stats_high_quality_transcriptions,
    get_total_good_transcribed_video_duration,
    get_stats_videos_with_low_transcription,
)
from app.services import BroadcasterService, VideoService, TranscriptionService, UserService
from app.cache import cache
from io import BytesIO
from app.rate_limit import limiter, rate_limit_exempt
import asyncio
from app.twitch_api import get_twitch_user
import os
import mimetypes
import glob
import json
from datetime import datetime
from app.models.config import config

root_blueprint = Blueprint('root', __name__, url_prefix='/',
                           template_folder='templates', static_folder='static')


@root_blueprint.route("/")
@limiter.shared_limit("1000 per day, 60 per minute", exempt_when=rate_limit_exempt, scope="normal")
@check_banned()
def index():
    logger.info("Loaded frontpage")
    broadcasters = BroadcasterService.get_all()
    return render_template("search.html", broadcasters=broadcasters)


@root_blueprint.route("/login", strict_slashes=False)
def login():
    return render_template("unauthorized.html")


@root_blueprint.route("/admin")
def access_denied():
    return render_template("errors/404.html")


@root_blueprint.route("/robots.txt")
def robots_txt() -> Response:
    """Serve robots.txt file"""
    logger.info("Loaded robots.txt")
    robots_content = """User-agent: *
Disallow: /admin
Disallow: /login
Disallow: /logout
Disallow: /users
"""
    return Response(robots_content, mimetype="text/plain")


@root_blueprint.route("/logout")
def logout():
    logout_user()
    flash("You have logged out")
    return render_template("unauthorized.html")


@root_blueprint.route("/users")
@require_permission(permissions=PermissionType.Admin)
def users():
    users = UserService.get_all()
    logger.info("Loaded users.html", extra={"user_id": current_user.id})
    return render_template(
        "users.html", users=users, permission_types=PermissionType
    )


@root_blueprint.route("/utils")
@login_required
@require_permission([PermissionType.Admin, PermissionType.Moderator])
def utils():
    logger.info("Loaded utils.html", extra={"user_id": current_user.id})
    return render_template("utils.html")


@root_blueprint.route("/utils/transcription_jobs")
@login_required
@require_permission([PermissionType.Admin, PermissionType.Moderator])
def list_transcription_jobs():
    cache_dir = os.path.abspath(os.path.join(
        config.cache_location, "transcription_jobs"))
    os.makedirs(cache_dir, exist_ok=True)

    # Find all metadata files
    metadata_files = glob.glob(os.path.join(cache_dir, "*.json"))
    jobs = []

    for metadata_file in metadata_files:
        # Skip result files
        if "_result.json" in metadata_file:
            continue

        try:
            with open(metadata_file, "r") as f:
                metadata = json.load(f)

            job_id = metadata.get("job_id")
            if not job_id:
                continue

            # Check if result file exists
            result_file = os.path.join(cache_dir, f"{job_id}_result.json")
            if os.path.exists(result_file):
                metadata["status"] = "completed"
                # Get file size
                metadata["result_size"] = os.path.getsize(result_file)
                # Get completion time from file modification time
                metadata["completed_at"] = datetime.fromtimestamp(
                    os.path.getmtime(result_file)).isoformat()

            jobs.append(metadata)
        except Exception as e:
            logger.error(f"Error reading metadata file {metadata_file}: {e}")

    # Sort jobs by creation time, newest first
    jobs.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    if not jobs:
        return "<p>No transcription jobs found.</p>"

    html = """
    <div class="table-responsive">
        <table class="table table-striped table-hover">
            <thead>
                <tr>
                    <th>Job ID</th>
                    <th>Filename</th>
                    <th>Status</th>
                    <th>Created</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
    """

    for job in jobs:
        job_id = job.get("job_id")
        original_filename = job.get("original_filename", "Unknown")
        status = job.get("status", "unknown")
        created_at = job.get("created_at", "")

        # Format the date for display
        try:
            created_date = datetime.fromisoformat(created_at)
            created_display = created_date.strftime("%Y-%m-%d %H:%M:%S")
        except:
            created_display = created_at

        # Generate action buttons based on status
        actions = """
        <div class="btn-group btn-group-sm" role="group">
        """

        if status == "completed":
            actions += f"""
            <div class="btn-group">
                <a href="{url_for('root.download_transcription_result', job_id=job_id)}" class="btn btn-primary btn-sm" target="_blank">JSON</a>
                <a href="{url_for('root.download_transcription_srt', job_id=job_id)}" class="btn btn-success btn-sm" target="_blank">SRT</a>
            </div>
            """

        actions += f"""
            <button class="btn btn-danger btn-sm" 
                hx-delete="{url_for('root.delete_transcription_job', job_id=job_id)}" 
                hx-confirm="Are you sure you want to delete this job?" 
                hx-target="#transcription-list"
            >Delete</button>
        </div>
        """

        # Status badge color
        status_class = {
            "pending": "bg-warning",
            "processing": "bg-info",
            "completed": "bg-success",
            "failed": "bg-danger"
        }.get(status, "bg-secondary")

        html += f"""
        <tr>
            <td>{job_id[:8]}...</td>
            <td>{original_filename}</td>
            <td><span class="badge {status_class}">{status}</span></td>
            <td>{created_display}</td>
            <td>{actions}</td>
        </tr>
        """

    html += """
            </tbody>
        </table>
    </div>
    """

    return html


@root_blueprint.route("/utils/transcription/<job_id>/download")
@login_required
@require_permission([PermissionType.Admin, PermissionType.Moderator])
def download_transcription_result(job_id):
    # Validate job_id to prevent directory traversal
    if not all(c.isalnum() or c == '-' for c in job_id):
        abort(400)

    logger.info("Downloading transcription result", extra={"job_id": job_id})
    cache_dir = os.path.abspath(os.path.join(
        config.cache_location, "transcription_jobs"))
    result_file = os.path.join(cache_dir, f"{job_id}_result.json")

    if not os.path.exists(result_file):
        abort(404)

    # Get original filename from metadata
    metadata_file = os.path.join(cache_dir, f"{job_id}.json")
    original_filename = "transcription.json"

    if os.path.exists(metadata_file):
        try:
            with open(metadata_file, "r") as f:
                metadata = json.load(f)
            original_name = metadata.get("original_filename", "transcription")
            original_filename = f"{os.path.splitext(original_name)[0]}_transcription.json"
        except:
            pass

    return send_file(
        result_file,
        mimetype="application/json",
        as_attachment=True,
        download_name=original_filename
    )


@root_blueprint.route("/utils/transcription/<job_id>/download-srt")
@login_required
@require_permission([PermissionType.Admin, PermissionType.Moderator])
def download_transcription_srt(job_id):
    # Validate job_id to prevent directory traversal
    if not all(c.isalnum() or c == '-' for c in job_id):
        abort(400)

    logger.info("Downloading transcription srt", extra={"job_id": job_id})
    cache_dir = os.path.abspath(os.path.join(
        config.cache_location, "transcription_jobs"))
    result_file = os.path.join(cache_dir, f"{job_id}_result.json")

    if not os.path.exists(result_file):
        abort(404, description="Transcription result not found")

    # Get original filename from metadata
    metadata_file = os.path.join(cache_dir, f"{job_id}.json")
    original_name = "transcription"

    if os.path.exists(metadata_file):
        try:
            with open(metadata_file, "r") as f:
                metadata = json.load(f)
            original_name = os.path.splitext(metadata.get(
                "original_filename", "transcription"))[0]
        except:
            pass

    try:
        # Read the JSON file
        with open(result_file, 'r') as f:
            transcription_data = json.load(f)

        srt_text = TranscriptionService.convert_to_srt(transcription_data)

        # Create a response with the SRT content
        response = make_response(srt_text)
        response.headers["Content-Type"] = "text/plain"
        response.headers["Content-Disposition"] = f"attachment; filename={original_name}_transcription.srt"
        return response

    except Exception as e:
        logger.error(
            f"Error converting transcription to SRT: {e}", exc_info=True)
        abort(500, description="Error converting transcription to SRT format")


@root_blueprint.route("/utils/upload_transcription/<job_id>", methods=["POST"])
@require_api_key
@csrf.exempt
def upload_transcription_result(job_id):
    # Validate job_id to prevent directory traversal
    if not all(c.isalnum() or c == '-' for c in job_id):
        abort(400)

    logger.info("Uploading transcription result", extra={"job_id": job_id})
    cache_dir = os.path.abspath(os.path.join(
        config.cache_location, "transcription_jobs"))
    metadata_path = os.path.join(cache_dir, f"{job_id}.json")

    if not os.path.exists(metadata_path):
        abort(404, description="Job not found")

    try:
        # Get the JSON data from the request
        data = request.get_json()
        if not data:
            abort(400, description="Invalid JSON data")

        # Save the transcription result
        result_path = os.path.join(cache_dir, f"{job_id}_result.json")
        with open(result_path, "w") as f:
            json.dump(data, f)

        # Update the metadata
        with open(metadata_path, "r") as f:
            metadata = json.load(f)

        metadata["status"] = "completed"
        metadata["completed_at"] = datetime.now().isoformat()

        with open(metadata_path, "w") as f:
            json.dump(metadata, f)

        logger.info(f"Transcription result uploaded for job {job_id}")

        return jsonify({"success": True})

    except Exception as e:
        logger.error(
            f"Error uploading transcription result: {e}", exc_info=True)
        abort(
            500, description=f"Error uploading transcription result: {str(e)}")


@root_blueprint.route("/utils/transcription/<job_id>", methods=["DELETE"])
@login_required
@require_permission([PermissionType.Admin, PermissionType.Moderator])
def delete_transcription_job(job_id):
    # Validate job_id to prevent directory traversal
    logger.info(f"Trying to delete job id {job_id}")
    # if not all(c.isalnum() or c == '-' for c in job_id):
    #     abort(400)

    logger.info("Deleting transcription job", extra={"job_id": job_id})
    cache_dir = os.path.abspath(os.path.join(
        config.cache_location, "transcription_jobs"))

    # Find all files related to this job
    job_files = glob.glob(os.path.join(cache_dir, f"{job_id}*"))

    for file_path in job_files:
        try:
            os.remove(file_path)
            logger.info(f"Deleted file {file_path}", extra={
                        "user_id": current_user.id})
        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {e}", extra={
                         "user_id": current_user.id})

    # Return the updated list
    return list_transcription_jobs()


@root_blueprint.route("/stats")
@cache.cached(timeout=600)
@limiter.limit("100 per day, 5 per minute", exempt_when=rate_limit_exempt)
def stats():
    logger.info("Loaded stats.html")
    return render_template(
        "stats.html",
        video_count=VideoService.get_count(),
        video_duration=get_total_good_transcribed_video_duration(),
        transcriptions_count=TranscriptionService.get_count(),
        transcriptions_hq_count=get_stats_high_quality_transcriptions(),
        transcriptions_lq_count=get_stats_videos_with_low_transcription(),
    )


@root_blueprint.route("/thumbnails/<int:video_id>")
# @cache.memoize(timeout=120)
@limiter.shared_limit("10000 per hour", exempt_when=rate_limit_exempt, scope="images")
def serve_thumbnails(video_id: int):
    try:
        video = VideoService.get_by_id(video_id)
        if video.thumbnail is not None:
            try:
                content = video.thumbnail.file.read()
            except Exception:
                return "404", 404
            response = make_response(
                send_file(
                    BytesIO(content),
                    mimetype="image/jpeg",
                    download_name=f"{video.id}.jpg",
                )
            )
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return response
    except:
        return "404", 404


@root_blueprint.route("/api/lookup_twitch_id")
@login_required
@require_permission(permissions=PermissionType.Admin)
def lookup_twitch_id():
    """API endpoint to look up a Twitch user ID by username"""
    username = request.args.get("username")
    if not username:
        return jsonify({"success": False, "error": "No username provided"})

    try:
        # Use the existing Twitch API function to look up the user
        user = asyncio.run(get_twitch_user(username))
        if user:
            return jsonify({"success": True, "user_id": user.id, "display_name": user.display_name})
        else:
            return jsonify({"success": False, "error": "User not found"})
    except Exception as e:
        logger.error(f"Error looking up Twitch user: {e}")
        return jsonify({"success": False, "error": str(e)})


@root_blueprint.route("/utils/download_audio/<job_id>")
@require_api_key
def serve_audio(job_id):
    try:
        # Validate job_id to prevent directory traversal
        if not all(c.isalnum() or c == '-' for c in job_id):
            abort(400)

        logger.info("Serving audio file", extra={"job_id": job_id})
        # Use absolute path to avoid any path issues
        cache_dir = os.path.abspath(os.path.join(
            config.cache_location, "transcription_jobs"))

        # Debug the cache directory path
        logger.info(f"Cache directory: {cache_dir}")

        # Find the audio file with the job_id prefix
        audio_file = None
        for ext in [".mp3", ".wav", ".ogg", ".m4a", ".flac"]:
            potential_file = os.path.join(cache_dir, f"{job_id}{ext}")
            logger.debug(f"Checking for file at {potential_file}")
            if os.path.exists(potential_file):
                audio_file = potential_file
                break

        if not audio_file:
            logger.error(
                f"Audio file not found for job {job_id} in {cache_dir}")
            # List files in the directory for debugging
            if os.path.exists(cache_dir):
                files = os.listdir(cache_dir)
                logger.debug(f"Files in directory: {files}")
            else:
                logger.error(f"Cache directory does not exist: {cache_dir}")
            abort(404, description="Audio file not found")

        logger.info(f"Serving audio file: {audio_file}")
        mimetype, _ = mimetypes.guess_type(audio_file)
        mimetype = mimetype or "application/octet-stream"

        return send_file(
            audio_file,
            mimetype=mimetype,
            as_attachment=True,
            download_name=os.path.basename(audio_file)
        )

    except Exception as e:
        # Log the error to aid debugging
        logger.error(f"Failed to serve audio for job {job_id}: {e}")
        abort(500, description="Internal Server Error")
