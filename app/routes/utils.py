from flask import Blueprint, render_template, redirect, request, url_for, flash, jsonify
from app.permissions import require_permission
from app.models import db
from app.models import (
    PermissionType,
)
from app.services import TranscriptionService
from app.logger import logger
from flask_login import current_user, login_required  # type: ignore
from datetime import datetime
from sqlalchemy import and_, or_, func
from app.permissions import require_permission, has_any_moderation_access, get_accessible_channels, require_api_key
from app.csrf import csrf
import os
import glob
import json
from app.models.config import config
utils_blueprint = Blueprint(
    'utils', __name__, url_prefix='/utils', template_folder='templates', static_folder='static')


@utils_blueprint.route("/")
@login_required
@require_permission([PermissionType.Admin, PermissionType.Moderator])
def utils():
    from app.services import ChannelService
    logger.info("Loaded utils.html", extra={"user_id": current_user.id})
    channels = ChannelService.get_all(show_hidden=False)
    # Convert to dictionaries for JSON serialization
    channels_data = [{"id": channel.id, "name": channel.name} for channel in channels]
    return render_template("utils.html", channels=channels_data)

@utils_blueprint.route("/recover_files")
@login_required
@require_permission([PermissionType.Admin])
def recover_files():
    from app.services.file_recovery import FileRecoveryService
    return FileRecoveryService.recover_files()

@utils_blueprint.route("/chatlog_search", methods=["POST"])
@login_required
@require_permission(check_broadcaster=True, check_moderator=True, permissions=PermissionType.Moderator)
def chatlog_search():
    from app.models import ChatLog, Channels, Video
    from datetime import datetime, timedelta
    
    # Check authorization using helper function
    if not has_any_moderation_access(current_user):
        return {"error": "Access denied"}, 401
    
    # Get accessible channels with chat collection enabled for this user
    accessible_channels = get_accessible_channels(current_user, chat_collection_only=True)
    accessible_channel_ids = [ch.id for ch in accessible_channels] if accessible_channels else []
    
    try:
        # Get JSON data from request
        data = request.get_json()
        if not data:
            return {"error": "No data provided"}, 400
        
        query = (data.get("query") or "").strip()
        username = (data.get("username") or "").strip()
        
        if not query and not username:
            return {"error": "Either search query or username is required"}, 400
        
        channel_id = data.get("channel_id")
        date_from = data.get("date_from")
        date_to = data.get("date_to")
        limit = min(data.get("limit", 100), 1000)  # Cap at 1000 results
        
        logger.info(f"User is searching chatlog for user: '%s', query '%s'", username, query, extra={"user_id": current_user.id})
        # Build the query
        search_query = db.session.query(ChatLog, Channels.name.label('channel_name')).join(Channels)
        
        # Text search in message content only (if query provided)
        if query:
            # Check if query is enclosed in quotes for strict mode
            trimmed_query = query.strip()
            if ((trimmed_query.startswith('"') and trimmed_query.endswith('"') and len(trimmed_query) > 1) or
                (trimmed_query.startswith("'") and trimmed_query.endswith("'") and len(trimmed_query) > 1)):
                # Strict mode: search for exact phrase (case insensitive)
                phrase = trimmed_query[1:-1]  # Remove quotes
                if phrase:
                    search_query = search_query.filter(
                        ChatLog.message.ilike(f"%{phrase}%")
                    )
            else:
                # Normal mode: search for individual terms (case insensitive)
                search_terms = query.split()
                for term in search_terms:
                    search_query = search_query.filter(
                        ChatLog.message.ilike(f"%{term}%")
                    )
        
        # Channel access filter - only show results from channels user can access
        if accessible_channel_ids:
            search_query = search_query.filter(ChatLog.channel_id.in_(accessible_channel_ids))
        else:
            # User has no accessible channels, return empty results
            return {
                "results": [],
                "total": 0,
                "query": query,
                "filters": {
                    "channel": None,
                    "username": username if username else None,
                    "date_from": date_from,
                    "date_to": date_to
                }
            }
        
        # Channel filter (specific channel if provided)
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


@utils_blueprint.route("/transcription_jobs")
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


@utils_blueprint.route("/transcription/<job_id>/download")
@login_required
@require_permission(check_broadcaster=True, check_moderator=True, permissions=PermissionType.Moderator)
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


@utils_blueprint.route("/transcription/<job_id>/download-srt")
@login_required
@require_permission(check_broadcaster=True, check_moderator=True, permissions=PermissionType.Moderator)
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


@utils_blueprint.route("/upload_transcription/<job_id>", methods=["POST"])
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


@utils_blueprint.route("/transcription/<job_id>", methods=["DELETE"])
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
