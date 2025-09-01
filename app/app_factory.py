
from flask import Flask, request, g, render_template
from flask_login import LoginManager, current_user, user_logged_in  # type: ignore
from flask_wtf.csrf import CSRFError # type: ignore
from sqlalchemy.exc import NoResultFound
from os import makedirs, environ
from uuid import uuid4

from werkzeug.exceptions import NotFound, Unauthorized, InternalServerError
from .cache import cache
from .models.config import config
from .models import db
from .models.auth import OAuth
from sqlalchemy_file.storage import StorageManager
from libcloud.storage.drivers.local import LocalStorageDriver
from .auth import discord_blueprint, twitch_blueprint, twitch_blueprint_bot
from .redis_client import RedisTaskQueue
from flask_cors import CORS
from app.logger import logger
from app.utils import download_nltk
from .routes.root import root_blueprint
from .routes.clip_queue import clip_queue_blueprint
from .routes.search import search_blueprint
from .routes.management import management_blueprint
from .routes.video import video_blueprint
from .routes.channel import channel_blueprint
from .routes.transcription import transcription_blueprint
from .routes.broadcaster import broadcaster_blueprint
from .routes.users import users_blueprint
from .routes.leaderboard import leaderboard_blueprint
from .routes.utils import utils_blueprint
from werkzeug.middleware.proxy_fix import ProxyFix
from .rate_limit import limiter
from .csrf import csrf
from app.services import (
    BroadcasterService, VideoService, TranscriptionService, SegmentService,
    UserService, ContentQueueService, ContentService, PlatformServiceRegistry, ChannelService
)
import mimetypes



def init_storage(container: str = "transcriptions"):
    makedirs(
        config.storage_location + "/" + container, 0o777, exist_ok=True
    )
    makedirs(
        config.storage_location + "/thumbnails", 0o777, exist_ok=True
    )


login_manager = LoginManager()
login_manager.login_view = "twitch.login"
init_storage()

container = LocalStorageDriver(
    config.storage_location).get_container("transcriptions")
thumbnail_container = LocalStorageDriver(
    config.storage_location).get_container("thumbnails")
StorageManager.add_storage("default", container)
StorageManager.add_storage("thumbnails", thumbnail_container)


@login_manager.user_loader
def load_user(oauth_id: int):
    try:
        return db.session.query(OAuth).filter_by(user_id=int(oauth_id)).one().user
    except NoResultFound:
        logger.error("User not found for OAuth ID: %s", oauth_id)
        return None


cors = CORS()


def create_app(overrides: dict | None = None):
    logger.info("Creating app")
    init_storage()
    download_nltk()
    app = Flask(__name__)
    app.secret_key = config.app_secret
    app.config["SQLALCHEMY_DATABASE_URI"] = config.database_uri
    if overrides:
        app.config.update(overrides)
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
    app.config["CELERY"] = dict(
        broker_url=config.redis_uri,
        result_backend=config.redis_uri,
        task_ignore_result=False,
        result_expires=3600,  # Results expire after 1 hour
        task_track_started=True,  # Track when tasks start
        task_routes={
            "app.tasks.default": {"queue": "default-queue"},
            "app.main.update_channels_last_active": {"queue": "priority-queue"},
            "app.main.task_transcribe_audio": {"queue": "gpu-queue"},
            "app.main.task_transcribe_file": {"queue": "gpu-queue"},
            "app.task_download_twitch_clip": {"queue": "celery"},
        },
    )
    environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    if config.debug:
        environ["OAUTHLIB_INSECURE_TRANSPORT"] = "true"

    # Set up request ID tracking
    @app.before_request
    def before_request():
        g.request_id = request.headers.get("X-Request-Id", str(uuid4()))

    # Add request ID to response headers
    @app.after_request
    def after_request(response):
        if hasattr(g, 'request_id'):
            response.headers.set("X-Request-Id", g.request_id)
        return response

    # Make version available in templates, used for cache busting
    @app.context_processor
    def inject_functions():
        return dict(
            version=str(config.version).strip(":"),
            broadcaster_service=BroadcasterService(),
            video_service=VideoService(),
            transcription_service=TranscriptionService(),
            segment_service=SegmentService(),
            content_queue_service=ContentQueueService(),
            content_service=ContentService(),
            user_service=UserService(),
            channel_service=ChannelService(),
            platform_service_registry=PlatformServiceRegistry(),
        )

    cache.init_app(app)
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    cors.init_app(app, resources={
                  r"/*": {"origins": config.app_url}}, supports_credentials=True)

    # Set up user login signal handler
    @user_logged_in.connect_via(app)
    def handle_user_login(sender, user, **extra):
        try:
            UserService().update_last_login(user.id)
            UserService.update_moderated_channels(user)
            logger.info("User logged in", extra={"user_id": user.id})
        except Exception as e:
            logger.error("Failed to update user last login", extra={"user_id": user.id, "error": str(e)})
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)  # type: ignore

    # Only initialize rate limiter when not in testing mode
    if not app.config.get("TESTING"):
        limiter._storage_uri = config.redis_uri
    else:
        limiter._storage_uri = "memory://"

    limiter.init_app(app)
    mimetypes.add_type('application/wasm', '.wasm')

    # 404 error handler
    @app.errorhandler(404)
    def handle_404(e):
        # Log 404 requests at debug level (not error level)
        logger.debug("404 Not Found", extra={
            "method": request.method,
            "url": request.url,
            "request_id": getattr(g, 'request_id', None)
        })
        try:
            return render_template('errors/404.html'), 404
        except:
            # Fallback if template doesn't exist
            return "404 Not Found", 404

    # Global exception handler for non-404 errors
    @app.errorhandler(Exception)
    def handle_exception(e):
        if not isinstance(e, NotFound):
            # Log the exception with full stack trace
            logger.error("Unhandled exception occurred", exc_info=True, extra={
                "exception_type": type(e).__name__,
                "exception_message": str(e),
                "endpoint": request.endpoint,
                "method": request.method,
                "url": request.url,
                "request_id": getattr(g, 'request_id', None)
            })
        if isinstance(e, Unauthorized):
            return render_template('errors/401.html'), 401
        if isinstance(e, InternalServerError):
            return render_template('errors/500.html'), 500
        if isinstance(e, CSRFError):
            return render_template('errors/generic.html', error_message="CSRF token expired, please refresh the page and try again"), 400
        
        # Re-raise the exception to let Flask handle it normally
        raise e

    app.register_blueprint(discord_blueprint, url_prefix="/login")
    app.register_blueprint(twitch_blueprint, url_prefix="/login")
    app.register_blueprint(twitch_blueprint_bot,
                           url_prefix="/login/bot", name="twitch_bot")
    app.register_blueprint(root_blueprint)
    app.register_blueprint(search_blueprint)
    app.register_blueprint(clip_queue_blueprint)
    app.register_blueprint(management_blueprint)
    app.register_blueprint(video_blueprint)
    app.register_blueprint(channel_blueprint)
    app.register_blueprint(transcription_blueprint)
    app.register_blueprint(broadcaster_blueprint)
    app.register_blueprint(users_blueprint)
    app.register_blueprint(leaderboard_blueprint)
    app.register_blueprint(utils_blueprint)
    return app


app = create_app()

# Initialize Redis task queue
redis_task_queue = RedisTaskQueue()
redis_task_queue.init()
