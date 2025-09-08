from flask import Blueprint, render_template, flash, send_file, make_response, abort, jsonify, request, Response
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
from app.services import VideoService, TranscriptionService, UserService
from io import BytesIO
from app.rate_limit import limiter, rate_limit_exempt
import asyncio
from app.twitch_api import get_twitch_user
import os
import mimetypes
from app.models.config import config
from app.routes.search import search_page
from app.chatlogparse import parse_log
import tempfile
from datetime import datetime
import redis

root_blueprint = Blueprint('root', __name__, url_prefix='/',
                           template_folder='templates', static_folder='static')

# Redis connection for release tracking
r = redis.Redis.from_url(config.redis_uri)


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


@root_blueprint.route("/about")
def about():
    logger.info("Loaded about.html")
    return render_template(
        "about.html",
        video_count=VideoService.get_count(),
        video_duration=get_total_good_transcribed_video_duration(),
        transcriptions_count=TranscriptionService.get_count(),
        transcriptions_hq_count=get_stats_high_quality_transcriptions(),
        transcriptions_lq_count=get_stats_videos_with_low_transcription(),
    )

@root_blueprint.route("/health")
@require_api_key
def health():
    from app.models import db
    from sqlalchemy import text
    try:
        db.session.execute(text("SELECT 1"))
        return "OK", 200
    except Exception as e:
        logger.error("Database connection failed with exception %s", e)
        return "ERROR", 500



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
@require_permission(check_broadcaster=True, permissions=[PermissionType.Admin, PermissionType.Moderator])
def upload_chatlog():
    """API endpoint to upload and parse chatlog files"""
    if 'chatlog_file' not in request.files:
        return jsonify({"success": False, "error": "No file provided"})
    
    file = request.files['chatlog_file']
    channel_id = request.form.get('channel_id')
    events_only_raw = request.form.get('events_only')
    events_only = events_only_raw == 'on'
    
    logger.info(f"Upload chatlog: events_only_raw='{events_only_raw}', events_only={events_only}", extra={
        "user_id": current_user.id,
        "events_only_raw": events_only_raw,
        "events_only": events_only
    })
    
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
                timezone_str=None,  # Auto-detect from file
                events_only=events_only
            )
            
            if import_record:
                if events_only:
                    message = f"Successfully imported channel events only. Import ID: {import_record.id}"
                else:
                    message = f"Successfully imported chat logs. Import ID: {import_record.id}"
            else:
                if events_only:
                    message = "Successfully imported channel events only (legacy format)"
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

@root_blueprint.route("/utils/match_chatlog_users", methods=["POST"])
@login_required
@require_permission([PermissionType.Admin, PermissionType.Moderator])
def match_chatlog_users():
    """Match ChatLog entries to Users by username"""
    try:
        logger.info("Starting ChatLog user matching process", extra={"user_id": current_user.id})
        
        # Call the generic service function
        results = UserService.match_chatlog_users(
            batch_size=1000,  # Process 1000 records per batch
            progress_callback=None  # No callback for synchronous web request
        )
        
        # Format results as HTML for HTMX response
        if results['status'] == 'success':
            if results['total_unmatched'] == 0:
                html = """
                <div class="alert alert-info">
                    <h5><i class="bi bi-info-circle me-2"></i>No Unmatched Records</h5>
                    <p>All ChatLog entries already have user associations.</p>
                </div>
                """
            else:
                html = f"""
                <div class="alert alert-success">
                    <h5><i class="bi bi-check-circle me-2"></i>Matching Completed Successfully</h5>
                    <div class="row">
                        <div class="col-md-6">
                            <strong>Processing Summary:</strong>
                            <ul class="list-unstyled mt-2">
                                <li>📊 Total unmatched records: <strong>{results['total_unmatched']:,}</strong></li>
                                <li>✅ Records processed: <strong>{results['total_processed']:,}</strong></li>
                                <li>🎯 Matches found: <strong>{results['total_matched']:,}</strong></li>
                                <li>💾 Records updated: <strong>{results['total_updated']:,}</strong></li>
                            </ul>
                        </div>
                        <div class="col-md-6">
                            <strong>Performance:</strong>
                            <ul class="list-unstyled mt-2">
                                <li>🕐 Started: {results['started_at'][:19].replace('T', ' ')}</li>
                                <li>🏁 Completed: {results['completed_at'][:19].replace('T', ' ')}</li>
                                <li>📈 Match rate: <strong>{(results['total_matched']/results['total_processed']*100):.1f}%</strong></li>
                            </ul>
                        </div>
                    </div>
                </div>
                """
        elif results['status'] == 'warning':
            html = f"""
            <div class="alert alert-warning">
                <h5><i class="bi bi-exclamation-triangle me-2"></i>Process Completed with Warnings</h5>
                <p>The matching process completed but encountered some issues:</p>
                <ul>
            """
            for error in results['errors']:
                html += f"<li>{error}</li>"
            html += """
                </ul>
            </div>
            """
        else:  # error status
            html = f"""
            <div class="alert alert-danger">
                <h5><i class="bi bi-exclamation-circle me-2"></i>Matching Process Failed</h5>
                <p>The matching process encountered errors:</p>
                <ul>
            """
            for error in results['errors']:
                html += f"<li>{error}</li>"
            html += f"""
                </ul>
                <small class="text-muted">
                    Started: {results['started_at'][:19].replace('T', ' ')}<br>
                    Failed: {results.get('completed_at', 'N/A')[:19].replace('T', ' ') if results.get('completed_at') else 'N/A'}
                </small>
            </div>
            """
        
        logger.info(f"ChatLog matching completed - Status: {results['status']}, Updated: {results.get('total_updated', 0)}", 
                   extra={"user_id": current_user.id})
        
        return html
        
    except Exception as e:
        logger.error(f"Error in ChatLog user matching: {str(e)}", extra={"user_id": current_user.id}, exc_info=True)
        return f"""
        <div class="alert alert-danger">
            <h5><i class="bi bi-exclamation-circle me-2"></i>Server Error</h5>
            <p>An unexpected error occurred during the matching process: <code>{str(e)}</code></p>
        </div>
        """


@root_blueprint.route("/release")
@login_required
@require_permission()
def release_page():
    """Release button page - only accessible to global admins and moderators"""
    # Check if release has already happened
    released = r.get("yappr_1_0_released") == b"true"
    
    launch_data = None
    if released:
        # Get launch metadata
        launch_data = r.hgetall("yappr_1_0_launch_data")
        # Convert bytes to strings for template
        if launch_data:
            launch_data = {k.decode('utf-8') if isinstance(k, bytes) else k: 
                          v.decode('utf-8') if isinstance(v, bytes) else v 
                          for k, v in launch_data.items()}
    
    return render_template("release_button.html", released=released, launch_data=launch_data)


@root_blueprint.route("/release-launch", methods=["POST"])
@login_required
@require_permission([PermissionType.Admin, PermissionType.Moderator])
@csrf.exempt  # CSRF is handled in the template
def release_launch():
    """Trigger the 1.0 release - can only be called once"""
    try:
        # Check if already released
        if r.get("yappr_1_0_released") == b"true":
            return jsonify({
                "success": False,
                "message": "YappR 1.0 has already been launched!"
            })
        
        # Mark as released atomically
        release_key = "yappr_1_0_released"
        if r.set(release_key, "true", nx=True):  # Only set if key doesn't exist
            # Log the historic moment
            logger.info("🎉 YappR 1.0 OFFICIALLY LAUNCHED! 🎉", extra={
                "user_id": current_user.id,
                "username": current_user.name,
                "event": "yappr_1_0_launch",
                "timestamp": "1.0 release"
            })
            
            # Store launch metadata
            launch_data = {
                "launched_by": current_user.id,
                "launched_by_username": current_user.name,
                "launch_timestamp": datetime.now().isoformat(),
                "version": "1.0.0"
            }
            r.hset("yappr_1_0_launch_data", mapping=launch_data)
            
            return jsonify({
                "success": True,
                "message": f"🚀 YappR 1.0 LAUNCHED by {current_user.name}! 🚀"
            })
        else:
            # Someone else beat us to it
            return jsonify({
                "success": False,
                "message": "YappR 1.0 has already been launched by someone else!"
            })
            
    except Exception as e:
        logger.error("Failed to launch YappR 1.0", extra={
            "user_id": current_user.id,
            "error": str(e)
        }, exc_info=True)
        return jsonify({
            "success": False,
            "message": "Launch failed due to technical difficulties. Try again!"
        })

