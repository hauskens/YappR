from flask import Blueprint, render_template, flash, send_from_directory, url_for, send_file, make_response, abort, jsonify, request, Response, redirect
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
from app.routes.search import search_page
from app.chatlogparse import parse_log
import tempfile
from app.models import ChatLog, Channels, ChatLogImport, db
from sqlalchemy import and_, or_, func

root_blueprint = Blueprint('root', __name__, url_prefix='/',
                           template_folder='templates', static_folder='static')


@root_blueprint.route("/")
@limiter.shared_limit("1000 per day, 60 per minute", exempt_when=rate_limit_exempt, scope="normal")
@check_banned()
def index():
    logger.info("Loaded frontpage")
    return search_page()


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
    from app.services import ChannelService
    logger.info("Loaded utils.html", extra={"user_id": current_user.id})
    channels = ChannelService.get_all(show_hidden=False)
    # Convert to dictionaries for JSON serialization
    channels_data = [{"id": channel.id, "name": channel.name} for channel in channels]
    return render_template("utils.html", channels=channels_data)


@root_blueprint.route("/utils/chatlog_search", methods=["POST"])
@login_required
@require_permission([PermissionType.Admin, PermissionType.Moderator])
def chatlog_search():
    from app.models import ChatLog, Channels, Video
    from sqlalchemy import and_, or_, func
    from datetime import datetime, timedelta
    
    try:
        # Get JSON data from request
        data = request.get_json()
        if not data:
            return {"error": "No data provided"}, 400
        
        query = (data.get("query") or "").strip()
        if not query:
            return {"error": "Search query is required"}, 400
        
        channel_id = data.get("channel_id")
        username = (data.get("username") or "").strip()
        date_from = data.get("date_from")
        date_to = data.get("date_to")
        limit = min(data.get("limit", 100), 1000)  # Cap at 1000 results
        
        # Build the query
        search_query = db.session.query(ChatLog, Channels.name.label('channel_name')).join(Channels)
        
        # Text search in message content
        search_terms = query.split()
        for term in search_terms:
            search_query = search_query.filter(
                or_(
                    ChatLog.message.ilike(f"%{term}%"),
                    ChatLog.username.ilike(f"%{term}%")
                )
            )
        
        # Channel filter
        if channel_id:
            search_query = search_query.filter(ChatLog.channel_id == channel_id)
        
        # Username filter
        if username:
            search_query = search_query.filter(ChatLog.username.ilike(f"%{username}%"))
        
        # Date filters
        if date_from:
            try:
                date_from_dt = datetime.fromisoformat(date_from)
                search_query = search_query.filter(ChatLog.timestamp >= date_from_dt)
            except ValueError:
                return {"error": "Invalid date_from format"}, 400
        
        if date_to:
            try:
                date_to_dt = datetime.fromisoformat(date_to + "T23:59:59")
                search_query = search_query.filter(ChatLog.timestamp <= date_to_dt)
            except ValueError:
                return {"error": "Invalid date_to format"}, 400
        
        # Get total count
        total_count = search_query.count()
        
        # Order by timestamp (newest first) and limit
        results = search_query.order_by(ChatLog.timestamp.desc()).limit(limit).all()
        
        # Format results with VOD links
        formatted_results = []
        for chatlog, channel_name in results:
            # Find matching VOD for this chatlog timestamp
            vod_info = find_matching_vod(chatlog.channel_id, chatlog.timestamp)
            
            result = {
                "id": chatlog.id,
                "username": chatlog.username,
                "message": chatlog.message,
                "timestamp": chatlog.timestamp.isoformat(),
                "channel_id": chatlog.channel_id,
                "channel_name": channel_name
            }
            
            # Add VOD information if available
            if vod_info:
                result["vod"] = vod_info
            
            formatted_results.append(result)
        
        # Determine channel name for filters response
        channel_name_filter = None
        if channel_id:
            channel = db.session.query(Channels).filter_by(id=channel_id).first()
            if channel:
                channel_name_filter = channel.name
        
        return {
            "results": formatted_results,
            "total": total_count,
            "query": query,
            "filters": {
                "channel": channel_name_filter,
                "username": username if username else None,
                "date_from": date_from,
                "date_to": date_to
            }
        }
        
    except Exception as e:
        logger.error(f"Error in chatlog search: {e}", extra={"user_id": current_user.id})
        return {"error": "Internal server error"}, 500


def find_matching_vod(channel_id: int, chatlog_timestamp: datetime):
    """Find a VOD that matches the chatlog timestamp with some tolerance."""
    from app.models import Video
    from app.services.video import VideoService
    from datetime import timedelta
    
    # Look for videos within a reasonable time window (e.g., 6 hours before and after)
    time_window = timedelta(hours=6)
    start_time = chatlog_timestamp - time_window
    end_time = chatlog_timestamp + time_window
    
    # Find videos from the same channel within the time window
    matching_video = db.session.query(Video).filter(
        and_(
            Video.channel_id == channel_id,
            Video.uploaded >= start_time,
            Video.uploaded <= end_time,
            Video.active == True
        )
    ).order_by(func.abs(func.extract('epoch', Video.uploaded - chatlog_timestamp))).first()
    
    if matching_video:
        # Calculate the timestamp offset within the VOD
        time_diff = chatlog_timestamp - matching_video.uploaded
        vod_timestamp_seconds = max(0, int(time_diff.total_seconds()))
        
        # Use VideoService to get the proper URL with timestamp
        video_url = VideoService.get_url_with_timestamp(matching_video, vod_timestamp_seconds)
        
        # Format timestamp as HH:MM:SS
        hours = int(vod_timestamp_seconds) // 3600
        minutes = (int(vod_timestamp_seconds) % 3600) // 60
        seconds = int(vod_timestamp_seconds) % 60
        timestamp_formatted = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        
        return {
            "video_id": matching_video.id,
            "video_title": matching_video.title,
            "platform_ref": matching_video.platform_ref,
            "timestamp_seconds": int(vod_timestamp_seconds),
            "timestamp_formatted": timestamp_formatted,
            "video_url": video_url
        }
    
    return None


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


@root_blueprint.route("/api/upload_chatlog", methods=["POST"])
@login_required
@csrf.exempt
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def upload_chatlog():
    """API endpoint to upload and parse chatlog files"""
    if 'chatlog_file' not in request.files:
        return jsonify({"success": False, "error": "No file provided"})
    
    file = request.files['chatlog_file']
    channel_id = request.form.get('channel_id')
    
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"})
    
    if not channel_id:
        return jsonify({"success": False, "error": "No channel ID provided"})
    
    try:
        channel_id = int(channel_id)
    except ValueError:
        return jsonify({"success": False, "error": "Invalid channel ID"})
    
    # Check if user has permission to upload for this channel
    # We need to verify the user owns/moderates the broadcaster
    from app.services import ChannelService
    from app.models import PermissionType
    
    try:
        channel = ChannelService.get_by_id(channel_id)
        if not channel:
            return jsonify({"success": False, "error": "Channel not found"})
        
        # Check permissions: admin, or broadcaster owner, or moderator
        user_service = UserService()
        if not (user_service.has_permission(current_user, [PermissionType.Admin]) or 
                user_service.has_broadcaster_id(current_user, channel.broadcaster.id) or
                user_service.is_moderator(current_user, channel.broadcaster.id)):
            return jsonify({"success": False, "error": "Permission denied"})
        
        # Validate file extension and filename
        allowed_extensions = {'.log', '.txt'}
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in allowed_extensions:
            return jsonify({"success": False, "error": "Invalid file type. Only .log and .txt files are allowed"})
        
        # Validate filename doesn't contain path traversal attempts
        if '..' in file.filename or '/' in file.filename or '\\' in file.filename:
            return jsonify({"success": False, "error": "Invalid filename"})
        
        # Check file size (limit to 50MB)
        MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)  # Reset file pointer
        
        if file_size > MAX_FILE_SIZE:
            return jsonify({"success": False, "error": "File too large. Maximum size is 50MB"})
        
        if file_size == 0:
            return jsonify({"success": False, "error": "File is empty"})
        
        # Create secure temporary file in system temp directory
        with tempfile.NamedTemporaryFile(mode='w+b', suffix=file_ext, delete=False, prefix='chatlog_') as temp_file:
            file.save(temp_file.name)
            temp_filename = temp_file.name
        
        try:
            # Parse the log file
            import_record = parse_log(
                log_path=temp_filename,
                channel_id=channel_id,
                imported_by=current_user.id,
                timezone_str=None  # Auto-detect from file
            )
            
            if import_record:
                message = f"Successfully imported chat logs. Import ID: {import_record.id}"
            else:
                message = "Successfully imported chat logs (legacy format)"
            
            logger.info(f"Chat log uploaded successfully: {file.filename}", extra={
                "user_id": current_user.id,
                "channel_id": channel_id,
                "import_id": import_record.id if import_record else None,
                "upload_filename": file.filename
            })
            
            return jsonify({
                "success": True, 
                "message": message,
                "import_id": import_record.id if import_record else None
            })
            
        except ValueError as e:
            # This handles duplicate detection and parsing errors
            error_msg = str(e)
            logger.warning(f"Chat log upload failed: {error_msg}", extra={
                "user_id": current_user.id,
                "channel_id": channel_id,
                "upload_filename": file.filename
            })
            
            # Provide user-friendly error messages
            if "duplicate messages" in error_msg:
                return jsonify({
                    "success": False, 
                    "error": "This chat log appears to contain messages that have already been imported. Duplicate imports are not allowed to prevent data corruption."
                })
            else:
                return jsonify({"success": False, "error": f"Invalid log format: {error_msg}"})
            
        except Exception as e:
            logger.error(f"Error parsing chat log: {str(e)}", extra={
                "user_id": current_user.id,
                "channel_id": channel_id,
                "upload_filename": file.filename
            }, exc_info=True)
            return jsonify({"success": False, "error": f"Error parsing log file: {str(e)}"})
        
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_filename)
            except:
                pass
    
    except Exception as e:
        logger.error(f"Error in chatlog upload: {str(e)}", extra={
            "user_id": current_user.id
        }, exc_info=True)
        return jsonify({"success": False, "error": f"Server error: {str(e)}"})


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


@root_blueprint.route("/utils/chatlog_imports")
@login_required
@require_permission([PermissionType.Admin, PermissionType.Moderator])
def list_chatlog_imports():
    """List all chatlog imports with their details"""
    try:
        from app.models.user import Users
        imports = db.session.query(ChatLogImport).join(Channels).join(Users, ChatLogImport.imported_by == Users.id).order_by(ChatLogImport.imported_at.desc()).all()
        
        if not imports:
            return "<p>No chatlog imports found.</p>"
        
        html = """
        <div class="table-responsive">
            <table class="table table-striped table-hover">
                <thead>
                    <tr>
                        <th>Import ID</th>
                        <th>Channel</th>
                        <th>Imported By</th>
                        <th>Import Date</th>
                        <th>Timezone</th>
                        <th>Messages</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        for import_record in imports:
            message_count = len(import_record.chatlogs)
            import_date = import_record.imported_at.strftime("%Y-%m-%d %H:%M:%S")
            
            html += f"""
            <tr>
                <td>{import_record.id}</td>
                <td>{import_record.channel.name}</td>
                <td>{import_record.imported_by_user.name}</td>
                <td>{import_date}</td>
                <td>
                    <span class="badge bg-secondary">{import_record.timezone}</span>
                </td>
                <td>{message_count:,}</td>
                <td>
                    <div class="btn-group btn-group-sm" role="group">
                        <button class="btn btn-warning btn-sm" 
                            onclick="window.showTimezoneModal({import_record.id}, '{import_record.timezone}')"
                            title="Adjust timezone">
                            <i class="bi bi-clock"></i>
                        </button>
                        <button class="btn btn-danger btn-sm" 
                            hx-delete="/utils/chatlog_imports/{import_record.id}" 
                            hx-confirm="Are you sure you want to delete this import and all its {message_count:,} messages?" 
                            hx-target="#chatlog-imports-container"
                            hx-on::after-request="window.loadChatlogImports()"
                            title="Delete import">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </td>
            </tr>
            """
        
        html += """
                </tbody>
            </table>
        </div>
        
        <!-- Timezone Adjustment Modal -->
        <div class="modal fade" id="timezoneModal" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Adjust Timezone</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <form id="timezoneForm">
                            <input type="hidden" id="import-id" name="import_id" />
                            <div class="mb-3">
                                <label for="current-timezone" class="form-label">Current Timezone</label>
                                <input type="text" class="form-control" id="current-timezone" readonly />
                            </div>
                            <div class="mb-3">
                                <label for="new-timezone" class="form-label">New Timezone</label>
                                <select class="form-control" id="new-timezone" name="new_timezone" required>
                                    <option value="">Select timezone...</option>
                                    <option value="UTC">UTC</option>
                                    <option value="US/Eastern">US/Eastern</option>
                                    <option value="US/Central">US/Central</option>
                                    <option value="US/Mountain">US/Mountain</option>
                                    <option value="US/Pacific">US/Pacific</option>
                                    <option value="Europe/London">Europe/London</option>
                                    <option value="Europe/Berlin">Europe/Berlin</option>
                                    <option value="Europe/Paris">Europe/Paris</option>
                                    <option value="Asia/Tokyo">Asia/Tokyo</option>
                                    <option value="Asia/Shanghai">Asia/Shanghai</option>
                                    <option value="Australia/Sydney">Australia/Sydney</option>
                                </select>
                                <div class="form-text">This will convert all timestamps in the import from the current timezone to the new timezone.</div>
                            </div>
                        </form>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                        <button type="button" class="btn btn-warning" onclick="window.adjustTimezone()">Adjust Timezone</button>
                    </div>
                </div>
            </div>
        </div>
        
        """
        
        return html
        
    except Exception as e:
        logger.error(f"Error listing chatlog imports: {e}", extra={"user_id": current_user.id})
        return "<div class='alert alert-danger'>Error loading chatlog imports</div>"


@root_blueprint.route("/utils/chatlog_imports/<int:import_id>", methods=["DELETE"])
@login_required
@require_permission([PermissionType.Admin, PermissionType.Moderator])
def delete_chatlog_import(import_id):
    """Delete a chatlog import and all its messages"""
    try:
        import_record = db.session.query(ChatLogImport).filter_by(id=import_id).first()
        if not import_record:
            return jsonify({"error": "Import not found"}), 404
        
        # Delete all associated chat logs first
        db.session.query(ChatLog).filter_by(import_id=import_id).delete()
        
        # Delete the import record
        db.session.delete(import_record)
        db.session.commit()
        
        logger.info(f"Deleted chatlog import {import_id}", extra={"user_id": current_user.id})
        
        # Return the updated list
        return list_chatlog_imports()
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting chatlog import {import_id}: {e}", extra={"user_id": current_user.id})
        return jsonify({"error": "Failed to delete import"}), 500


@root_blueprint.route("/utils/chatlog_imports/<int:import_id>/adjust_timezone", methods=["POST"])
@login_required
@require_permission([PermissionType.Admin, PermissionType.Moderator])
def adjust_chatlog_timezone(import_id):
    """Adjust timezone for all messages in a chatlog import"""
    try:
        data = request.get_json()
        if not data or 'new_timezone' not in data:
            return jsonify({"error": "New timezone is required"}), 400
        
        new_timezone = data['new_timezone']
        
        import_record = db.session.query(ChatLogImport).filter_by(id=import_id).first()
        if not import_record:
            return jsonify({"error": "Import not found"}), 404
        
        # Import timezone libraries
        from datetime import timezone
        from zoneinfo import ZoneInfo
        
        try:
            old_tz = ZoneInfo(import_record.timezone)
            new_tz = ZoneInfo(new_timezone)
        except Exception as e:
            return jsonify({"error": f"Invalid timezone: {e}"}), 400
        
        # Store old timezone before updating
        old_timezone = import_record.timezone
        
        # Get all chat logs for this import
        chat_logs = db.session.query(ChatLog).filter_by(import_id=import_id).all()
        
        updated_count = 0
        for chat_log in chat_logs:
            # Convert timestamp from old timezone to new timezone
            # Assume the stored timestamp is naive and in the old timezone
            if chat_log.timestamp.tzinfo is None:
                # Make it timezone-aware in the old timezone
                old_time = chat_log.timestamp.replace(tzinfo=old_tz)
            else:
                old_time = chat_log.timestamp.astimezone(old_tz)
            
            # Convert to new timezone and make naive again for storage
            new_time = old_time.astimezone(new_tz).replace(tzinfo=None)
            chat_log.timestamp = new_time
            updated_count += 1
        
        # Update the import record's timezone
        import_record.timezone = new_timezone
        
        db.session.commit()
        
        logger.info(f"Adjusted timezone for import {import_id} from {old_timezone} to {new_timezone}, updated {updated_count} messages", 
                   extra={"user_id": current_user.id})
        
        return jsonify({
            "success": True, 
            "message": f"Successfully updated {updated_count:,} messages to {new_timezone} timezone"
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adjusting timezone for import {import_id}: {e}", extra={"user_id": current_user.id})
        return jsonify({"error": f"Failed to adjust timezone: {str(e)}"}), 500


@root_blueprint.route("/utils/timezone_info")
@login_required
@require_permission([PermissionType.Admin, PermissionType.Moderator])
def timezone_info():
    """Display server timezone information for debugging"""
    tz_info = config.server_timezone_info
    
    html = f"""
    <div class="alert alert-info">
        <h5><i class="bi bi-info-circle me-2"></i>Server Timezone Information</h5>
        <table class="table table-sm table-borderless">
    """
    
    for key, value in tz_info.items():
        html += f"<tr><td><strong>{key.replace('_', ' ').title()}:</strong></td><td>{value}</td></tr>"
    
    html += """
        </table>
        <div class="mt-3">
            <small class="text-muted">
                This information helps debug timezone issues with ChatLog imports. 
                The server should automatically detect the local timezone, but you can override it with the TIMEZONE environment variable.
            </small>
        </div>
    </div>
    """
    
    return html
