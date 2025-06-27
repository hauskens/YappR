from flask import Flask, request, g
from flask_bootstrap import Bootstrap5 # type: ignore
from flask_login import LoginManager, current_user # type: ignore
from flask_caching import Cache
from sqlalchemy.exc import NoResultFound
from os import makedirs, environ
from uuid import uuid4
from .cache import cache
from .models.config import config
from .models.db import db, OAuth
from sqlalchemy_file.storage import StorageManager
from libcloud.storage.drivers.local import LocalStorageDriver
from .auth import discord_blueprint, twitch_blueprint, twitch_blueprint_bot
from .redis_client import RedisTaskQueue
from flask_cors import CORS
from flask_socketio import SocketIO
from app.logger import logger
from .routes.root import root_blueprint
from .routes.clip_queue import clip_queue_blueprint
from .routes.search import search_blueprint
from .routes.management import management_blueprint
from .routes.video import video_blueprint
from .routes.channel import channel_blueprint
from .routes.transcription import transcription_blueprint
from .routes.broadcaster import broadcaster_blueprint
from .routes.users import users_blueprint
from werkzeug.middleware.proxy_fix import ProxyFix
from .rate_limit import limiter


socketio = SocketIO()
def init_storage(container: str = "transcriptions"):
    makedirs(
        config.storage_location + "/" + container, 0o777, exist_ok=True
    ) 
    makedirs(
        config.storage_location + "/thumbnails", 0o777, exist_ok=True
    ) 


bootstrap = Bootstrap5()

login_manager = LoginManager()
login_manager.login_view = "discord.login"

init_storage()

container = LocalStorageDriver(config.storage_location).get_container("transcriptions")
thumbnail_container = LocalStorageDriver(config.storage_location).get_container("thumbnails")
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
    app = Flask(__name__)
    app.secret_key = config.app_secret
    app.config["SQLALCHEMY_DATABASE_URI"] = config.database_uri
    if overrides:
        app.config.update(overrides)
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
    app.config["CELERY"] = dict(
        broker_url=config.redis_uri,
        backend=config.database_uri,
        task_ignore_result=True,
        task_routes={
            "app.tasks.default": {"queue": "default-queue"},
            "app.main.update_channels_last_active": {"queue": "priority-queue"},
            "app.main.task_transcribe_audio": {"queue": "gpu-queue"},
            "app.main.task_transcribe_file": {"queue": "gpu-queue"},
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
    
    cache.init_app(app)
    db.init_app(app)
    login_manager.init_app(app)
    bootstrap.init_app(app)
    cors.init_app(app, resources={r"/*": {"origins": config.app_url}}, supports_credentials=True)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    # app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    socketio.init_app(app)
    
    # Only initialize rate limiter when not in testing mode
    if not app.config.get("TESTING"):
        limiter._storage_uri = config.redis_uri
    else:
        limiter._storage_uri = "memory://"
    
    limiter.init_app(app)
    

    app.register_blueprint(discord_blueprint, url_prefix="/login")
    app.register_blueprint(twitch_blueprint, url_prefix="/login")
    app.register_blueprint(twitch_blueprint_bot, url_prefix="/login/bot", name="twitch_bot")
    app.register_blueprint(root_blueprint)
    app.register_blueprint(search_blueprint)
    app.register_blueprint(clip_queue_blueprint)
    app.register_blueprint(management_blueprint)
    app.register_blueprint(video_blueprint)
    app.register_blueprint(channel_blueprint)
    app.register_blueprint(transcription_blueprint)
    app.register_blueprint(broadcaster_blueprint)
    app.register_blueprint(users_blueprint)
    return app


app = create_app()

# Initialize Redis task queue
redis_task_queue = RedisTaskQueue()
redis_task_queue.init()
