from flask import Blueprint, render_template, request, session
from app.logger import logger
from app.services import BroadcasterService
from app.rate_limit import limiter, rate_limit_exempt
from app.search import search_v2
from app.utils import get_valid_date

search_blueprint = Blueprint('search', __name__, url_prefix='/search',
                             template_folder='templates', static_folder='static')


@search_blueprint.route("", strict_slashes=False)
@limiter.shared_limit("1000 per day, 60 per minute", exempt_when=rate_limit_exempt, scope="normal")
def search_page():
    broadcasters = BroadcasterService.get_all()
    logger.info(f"Loaded search.html")
    return render_template("search.html", broadcasters=broadcasters)


@search_blueprint.route("", methods=["POST"], strict_slashes=False)
@limiter.shared_limit("100 per day, 5 per minute", exempt_when=rate_limit_exempt, scope="query")
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
