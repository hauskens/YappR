from flask import Blueprint, render_template, request, session
from app.logger import logger
from app.rate_limit import limiter, rate_limit_exempt
from app.search import search_v2
from app.utils import get_valid_date
from app.permissions import check_banned
from app.services import UserService, ModerationService, BroadcasterService 
from flask_login import current_user # type: ignore

search_blueprint = Blueprint('search', __name__, url_prefix='/search',
                             template_folder='templates', static_folder='static')


@search_blueprint.route("", strict_slashes=False)
@limiter.shared_limit("1000 per day, 60 per minute", exempt_when=rate_limit_exempt, scope="normal")
@check_banned()
def search_page():
    if current_user.is_anonymous:
        broadcasters = BroadcasterService.get_all(show_hidden=False)

    elif UserService.is_moderator(current_user) or UserService.is_admin(current_user):
        broadcasters = BroadcasterService.get_all(show_hidden=True)
    else:
        all_broadcasters = BroadcasterService.get_all(show_hidden=False)
        banned_channel_ids = ModerationService.get_banned_channel_ids(current_user)
        banned_broadcaster_ids = [BroadcasterService.get_by_internal_channel_id(channel_id).id for channel_id in banned_channel_ids]

        broadcasters = [broadcaster for broadcaster in all_broadcasters if broadcaster.id not in banned_broadcaster_ids]
    if not current_user.is_anonymous and UserService.is_broadcaster(current_user):
        broadcasters.append(UserService.get_broadcaster(current_user))
    logger.info(f"Loaded search.html")
    return render_template("search.html", broadcasters=broadcasters)


@search_blueprint.route("", methods=["POST"], strict_slashes=False)
@limiter.shared_limit("100 per day, 5 per minute", exempt_when=rate_limit_exempt, scope="query")
@check_banned()
def search_word():
    logger.info("User searching something..")
    search_term = request.form["search"]
    broadcaster_id = int(request.form["broadcaster"])
    session["last_selected_broadcaster"] = broadcaster_id

    start_date = get_valid_date(request.form.get("start_date", ""))
    end_date = get_valid_date(request.form.get("end_date", ""))
    channel_type = request.form.get("channel_type", "all")
    broadcaster = BroadcasterService.get_by_id(broadcaster_id)
    channels = [
        channel
        for channel in broadcaster.channels
        if str(channel.platform_name).lower() == channel_type or channel_type == "all"
    ]
    logger.info("channels: %s", len(channels))
    video_result = search_v2(search_term, channels, start_date, end_date)
    transcription_stats = BroadcasterService.get_transcription_stats(
        broadcaster_id)
    return render_template(
        "result.html",
        search_word=search_term,
        broadcaster=broadcaster,
        video_result=video_result,
        transcription_stats=transcription_stats,
    )
