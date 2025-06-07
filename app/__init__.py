import logging
import os
from flask import Flask
from flask_bootstrap import Bootstrap5
from flask_login import LoginManager, current_user, login_user
from flask_dance.consumer import oauth_authorized
from flask_dance.contrib.discord import make_discord_blueprint
from flask_dance.consumer.storage.sqla import SQLAlchemyStorage
from werkzeug.middleware.proxy_fix import ProxyFix
from sqlalchemy.exc import NoResultFound
from os import makedirs, environ
from datetime import timedelta
from .models.config import config
from .models.db import db, OAuth, Users, AccountSource
from sqlalchemy_file.storage import StorageManager
from libcloud.storage.drivers.local import LocalStorageDriver
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from .auth import discord_blueprint, twitch_blueprint, twitch_blueprint_bot
from .redis_client import RedisTaskQueue
from flask_cors import CORS, cross_origin
from flask_socketio import SocketIO, emit, send
from loki_logger_handler.loki_logger_handler import LokiLoggerHandler



logger = logging.getLogger("custom_logger")
logger.setLevel(config.log_level)

# Add Loki handler if Loki URL is provided
if config.loki_url:
    custom_handler = LokiLoggerHandler(
        url=config.loki_url,
        labels={"application": "yappr", "environment": config.environment, "service": config.service_name, "version": os.getenv("VERSION", "unknown")},
        label_keys={},
        enable_structured_loki_metadata=True,
        timeout=10,
    )
    logger.addHandler(custom_handler)
    
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
        logger.error(f"User not found for OAuth ID: {oauth_id}")
        return None

        

def create_app():
    init_storage()
    app = Flask(__name__)
    app.secret_key = config.app_secret
    app.config["SQLALCHEMY_DATABASE_URI"] = config.database_uri
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
    app.config["CELERY"] = dict(
        broker_url=config.redis_uri,
        backend=config.database_uri,
        task_ignore_result=True,
        task_routes={
            "app.tasks.default": {"queue": "default-queue"},
            "app.main.task_transcribe_audio": {"queue": "gpu-queue"},
        },
    )
    environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    if config.debug:
        environ["OAUTHLIB_INSECURE_TRANSPORT"] = "true"
    db.init_app(app)
    login_manager.init_app(app)
    bootstrap.init_app(app)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    cors = CORS(app, resources={r"/*": {"origins": "http://localhost:" + str(config.app_port)}})
    socketio.init_app(app)
    

    app.register_blueprint(discord_blueprint, url_prefix="/login")
    app.register_blueprint(twitch_blueprint, url_prefix="/login")
    app.register_blueprint(twitch_blueprint_bot, url_prefix="/login/bot", name="twitch_bot")
    return app


app = create_app()

# Initialize Redis task queue
redis_task_queue = RedisTaskQueue()
redis_task_queue.init()

# Configure rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["2000 per day", "200 per hour"],
    storage_uri=config.redis_uri
)

# Custom rate limit exemption for authenticated users
def rate_limit_exempt():
    return current_user.is_anonymous == False
