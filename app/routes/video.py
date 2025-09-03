from flask import Blueprint, render_template, redirect, request, url_for, abort, jsonify
from app.permissions import require_permission, require_api_key
from app.logger import logger
from app.models import db
from app.models import PermissionType, ChatLog
from flask_login import login_required, current_user  # type: ignore
from app.cache import cache, make_cache_key
from app.rate_limit import limiter, rate_limit_exempt
from datetime import timedelta, datetime
from io import BytesIO
from flask import send_file
import mimetypes
from app.services import VideoService, UserService, ChannelService
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
        return "You do not have access", 401


@video_blueprint.route("/<int:video_id>/edit")
@login_required
@limiter.shared_limit("1000 per day, 60 per minute", exempt_when=rate_limit_exempt, scope="normal")
@require_permission(check_anyone=True)
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

    def get_all_chat_logs(search_term=None):
        """Get chat logs from current video and linked source videos"""
        all_logs = []
        
        # Get chatlogs from current video
        base_query = db.session.query(ChatLog).filter(
            ChatLog.channel_id == video.channel_id,
            ChatLog.timestamp >= start_time,
            ChatLog.timestamp <= end_time
        )
        
        if search_term:
            base_query = base_query.filter(ChatLog.message.contains(search_term))
            
        current_logs = base_query.all()
        all_logs.extend(current_logs)
        
        # Get chatlogs from linked source videos
        for mapping in video.target_mappings:
            if not mapping.active:
                continue
                
            source_video = mapping.source_video
            source_start = source_video.uploaded + timedelta(seconds=mapping.source_start_time)
            source_end = source_video.uploaded + timedelta(seconds=mapping.source_end_time)
            
            source_query = db.session.query(ChatLog).filter(
                ChatLog.channel_id == source_video.channel_id,
                ChatLog.timestamp >= source_start,
                ChatLog.timestamp <= source_end
            )
            
            if search_term:
                source_query = source_query.filter(ChatLog.message.contains(search_term))
                
            source_logs = source_query.all()
            all_logs.extend(source_logs)
        
        return sorted(all_logs, key=lambda x: x.timestamp)

    if request.method == "POST":
        search = request.form.get("chatSearchInput")
        user_filter = request.form.get("userFilter")
        logger.info("chat search: %s, user filter: %s", search,
                    user_filter, extra={"video_id": video_id})

        chat_logs = get_all_chat_logs(search)
        return render_template(
            "video_chatlogs.html",
            chat_logs=chat_logs,
            video=video
        )
    else:
        chat_logs = get_all_chat_logs()
        
        formatted_logs = []
        for log in chat_logs:
            # Calculate offset based on which video this log belongs to
            if log.channel_id == video.channel_id:
                # Log from current video
                offset_seconds = (log.timestamp - start_time).total_seconds()
            else:
                # Log from source video - find the mapping and translate timestamp
                offset_seconds = None
                for mapping in video.target_mappings:
                    if mapping.active and log.channel_id == mapping.source_video.channel_id:
                        source_start = mapping.source_video.uploaded + timedelta(seconds=mapping.source_start_time)
                        source_offset = (log.timestamp - source_start).total_seconds()
                        # Translate source timestamp to target timestamp
                        target_timestamp = mapping.translate_source_to_target(source_offset)
                        if target_timestamp is not None:
                            offset_seconds = target_timestamp
                            break
                
                # Fallback if translation fails
                if offset_seconds is None:
                    offset_seconds = (log.timestamp - start_time).total_seconds()
            
            formatted_logs.append({
                "id": log.id,
                "username": log.username,
                "message": log.message,
                "timestamp": log.timestamp.isoformat(),
                "offset_seconds": offset_seconds
            })
        
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
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator], check_broadcaster=True, check_moderator=True)
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
@require_permission(check_anyone=True)
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


@video_blueprint.route("/<int:video_id>/link_preview")
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def video_link_preview(video_id: int):
    """Preview potential video links for this video"""
    video = VideoService.get_by_id(video_id)
    if not video:
        return jsonify({"error": "Video not found"}), 404
    
    # Get existing mappings for this video
    existing_mappings = []
    for mapping in video.target_mappings:
        if mapping.active:
            existing_mappings.append({
                "id": mapping.id,
                "source_video": {
                    "id": mapping.source_video.id,
                    "title": mapping.source_video.title,
                    "url": VideoService.get_url(mapping.source_video)
                },
                "source_start": mapping.source_start_time,
                "source_end": mapping.source_end_time,
                "target_start": mapping.target_start_time,
                "target_end": mapping.target_end_time,
                "time_offset": mapping.time_offset
            })
    
    # Find the source channel for this video's channel
    channel = video.channel
    if not channel.source_channel:
        return jsonify({"error": "No source channel configured for linking"}), 400
    
    # Get potential matches using the enhanced linking logic
    from app.utils import extract_date_from_video_title
    
    potential_matches = []
    margin_sec = 2
    min_duration = 300
    date_margin_hours = 48
    
    # Title parsing is always enabled
    title_parsing_enabled = True
    
    # Extract date from current video title
    estimated_date = extract_date_from_video_title(video.title)
    
    for source_video in channel.source_channel.videos:
        if source_video.id == video.id:  # Skip self
            continue
            
        match_reasons = []
        
        # Duration matching
        duration_match = (
            video.duration > min_duration
            and (source_video.duration - margin_sec)
            <= video.duration
            <= (source_video.duration + margin_sec)
        )
        if duration_match:
            match_reasons.append("duration")
        
        # Date matching
        date_match = False
        time_diff_hours = None
        if title_parsing_enabled and estimated_date and source_video.uploaded:
            time_diff = abs((estimated_date - source_video.uploaded).total_seconds() / 3600)
            time_diff_hours = time_diff
            date_match = time_diff <= date_margin_hours
            if date_match:
                match_reasons.append("date")
        
        # Include if either match
        if duration_match or date_match:
            potential_matches.append({
                "video": {
                    "id": source_video.id,
                    "title": source_video.title,
                    "uploaded": source_video.uploaded.isoformat(),
                    "duration": source_video.duration,
                    "platform": source_video.channel.platform_name,
                    "url": VideoService.get_url(source_video)
                },
                "match_reasons": match_reasons,
                "duration_diff": abs(video.duration - source_video.duration),
                "time_diff_hours": time_diff_hours
            })
    
    # Sort by match quality (prefer multiple reasons, then smaller differences)
    potential_matches.sort(key=lambda x: (
        -len(x["match_reasons"]),  # More reasons first
        x["duration_diff"],  # Smaller duration diff first
        x["time_diff_hours"] if x["time_diff_hours"] else float('inf')  # Smaller time diff first
    ))
    
    return jsonify({
        "video": {
            "id": video.id,
            "title": video.title,
            "duration": video.duration,
            "estimated_date": estimated_date.isoformat() if estimated_date else None,
            "title_parsing_enabled": title_parsing_enabled
        },
        "potential_matches": potential_matches[:10],  # Limit to top 10 matches
        "existing_mappings": existing_mappings
    })


@video_blueprint.route("/<int:video_id>/link_confirm", methods=["POST"])
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def video_link_confirm(video_id: int):
    """Confirm and create a video link"""
    video = VideoService.get_by_id(video_id)
    if not video:
        return jsonify({"error": "Video not found"}), 404
    
    if video.is_linked_to_source():
        return jsonify({"error": "Video is already linked"}), 400
    
    data = request.get_json()
    source_video_id = data.get("source_video_id")
    
    if not source_video_id:
        return jsonify({"error": "Source video ID is required"}), 400
    
    # Verify the source video exists and belongs to the correct channel
    source_video = VideoService.get_by_id(source_video_id)
    if not source_video:
        return jsonify({"error": "Source video not found"}), 404
    
    if source_video.channel_id != video.channel.source_channel_id:
        return jsonify({"error": "Source video must be from the configured source channel"}), 400
    
    # Create the timestamp mapping (default full video mapping)
    VideoService.add_timestamp_mapping(video, source_video)
    
    # Set estimated upload time if it was parsed from title
    if not video.estimated_upload_time:
        from app.utils import extract_date_from_video_title
        estimated_date = extract_date_from_video_title(video.title)
        if estimated_date:
            video.estimated_upload_time = estimated_date
    
    db.session.commit()
    
    logger.info(f"Linked video {video_id} to source video {source_video_id}", 
                extra={"video_id": video_id, "source_video_id": source_video_id, "user_id": current_user.id})
    
    return jsonify({
        "success": True,
        "message": f"Successfully linked to {source_video.title}",
        "source_video": {
            "id": source_video.id,
            "title": source_video.title,
            "url": VideoService.get_url(source_video)
        }
    })

@video_blueprint.route("/mapping/<int:mapping_id>/remove", methods=["DELETE"])
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def remove_timestamp_mapping(mapping_id: int):
    """Remove a timestamp mapping"""
    success = VideoService.remove_timestamp_mapping(mapping_id)
    
    if success:
        logger.info(f"Removed timestamp mapping {mapping_id}", 
                    extra={"mapping_id": mapping_id, "user_id": current_user.id})
        return jsonify({
            "success": True,
            "message": "Timestamp mapping removed successfully"
        })
    else:
        return jsonify({"error": "Mapping not found or could not be removed"}), 404


@video_blueprint.route("/<int:video_id>/adjust_offset", methods=["POST"])
@login_required
@require_permission(permissions=[PermissionType.Admin, PermissionType.Moderator])
def video_adjust_offset(video_id: int):
    """Adjust time offset for all timestamp mappings of a video"""
    video = VideoService.get_by_id(video_id)
    if not video:
        return jsonify({"error": "Video not found"}), 404
    
    data = request.get_json()
    offset_adjustment = data.get("offset_adjustment")
    
    if offset_adjustment is None:
        return jsonify({"error": "offset_adjustment parameter is required"}), 400
    
    try:
        offset_adjustment = float(offset_adjustment)
    except (ValueError, TypeError):
        return jsonify({"error": "offset_adjustment must be a number"}), 400
    
    # Adjust all active timestamp mappings for this video
    updated_count = 0
    for mapping in video.target_mappings:
        if mapping.active:
            new_offset = mapping.time_offset + offset_adjustment
            mapping.adjust_time_offset(new_offset)
            updated_count += 1
    
    db.session.commit()
    
    logger.info(f"Adjusted time offset by {offset_adjustment}s for {updated_count} mappings", 
                extra={"video_id": video_id, "offset_adjustment": offset_adjustment, 
                       "updated_mappings": updated_count, "user_id": current_user.id})
    
    return jsonify({
        "success": True,
        "message": f"Adjusted offset by {offset_adjustment}s for {updated_count} timestamp mappings",
        "updated_count": updated_count
    })

