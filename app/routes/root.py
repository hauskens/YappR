from flask import Blueprint, render_template, flash, send_from_directory, redirect, url_for, send_file, make_response, abort, jsonify
from app.logger import logger
from flask_login import current_user, logout_user, login_required # type: ignore
from app.permissions import require_permission
from app.models.db import PermissionType
from app.retrievers import get_users, get_stats_videos, get_total_video_duration, get_stats_segments, get_stats_transcriptions, get_stats_high_quality_transcriptions, get_video
from app.cache import cache, make_cache_key
from app.rate_limit import limiter, rate_limit_exempt
from io import BytesIO
import asyncio
from app.twitch_api import get_twitch_user

root_blueprint = Blueprint('root', __name__, url_prefix='/', template_folder='templates', static_folder='static')
@root_blueprint.route("/")
# @limiter.shared_limit("1000 per day, 60 per minute", exempt_when=rate_limit_exempt, scope="normal")
def index():
    logger.info("Loaded frontpage")
    return redirect(url_for("search.search_page"))


@root_blueprint.route("/login")
def login():
    return render_template("unauthorized.html")

@root_blueprint.route("/admin")
# @limiter.shared_limit("10000 per hour", exempt_when=rate_limit_exempt, scope="images")
def access_denied():
    logger.warning("Access denied", extra={"user_id": current_user.id if not current_user.is_anonymous else None})
    return send_from_directory("static", "401.jpg")

@root_blueprint.route("/logout")
def logout():
    logout_user()
    flash("You have logged out")
    return render_template("unauthorized.html")

@root_blueprint.route("/users")
@require_permission(permissions=PermissionType.Admin)
def users():
    users = get_users()
    logger.info("Loaded users.html", extra={"user_id": current_user.id})
    return render_template(
        "users.html", users=users, permission_types=PermissionType
    )
    
@root_blueprint.route("/stats")
@cache.cached(timeout=600, make_cache_key=make_cache_key)
@limiter.limit("100 per day, 5 per minute", exempt_when=rate_limit_exempt)
def stats():
    logger.info("Loaded stats.html")
    return render_template(
        "stats.html",
        video_count="{:,}".format(get_stats_videos()),
        video_duration="{:,}".format(get_total_video_duration()),
        segment_count="{:,}".format(get_stats_segments()),
        transcriptions_count="{:,}".format(get_stats_transcriptions()),
        transcriptions_hq_count="{:,}".format(get_stats_high_quality_transcriptions()),
    )

@root_blueprint.route("/thumbnails/<int:video_id>")
@cache.memoize(timeout=120)
@limiter.shared_limit("10000 per hour", exempt_when=rate_limit_exempt, scope="images")
def serve_thumbnails(video_id: int):
    try:
        video = get_video(video_id)
        if video.thumbnail is not None:
            content = video.thumbnail.file.read()
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
        abort(404)
    abort(500)


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