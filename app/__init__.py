import logging
from flask import Flask
from flask_bootstrap import Bootstrap5
from flask_login import LoginManager, current_user, login_user
from flask_dance.consumer import oauth_authorized
from flask_dance.contrib.discord import make_discord_blueprint
from flask_dance.consumer.storage.sqla import SQLAlchemyStorage
from werkzeug.middleware.proxy_fix import ProxyFix
from sqlalchemy.exc import NoResultFound
from os import makedirs, environ
from .models.config import config
from .models.db import db, OAuth, Users, AccountSource
from sqlalchemy_file.storage import StorageManager
from libcloud.storage.drivers.local import LocalStorageDriver

logger = logging.getLogger(__name__)


def init_storage(container: str = "transcriptions"):
    makedirs(
        config.storage_location + "/" + container, 0o777, exist_ok=True
    )  # Ensure storage folder exists


bootstrap = Bootstrap5()

login_manager = LoginManager()
login_manager.login_view = "discord.login"

init_storage()
blueprint = make_discord_blueprint(
    client_id=config.discord_client_id,
    client_secret=config.discord_client_secret,
    scope=["identify"],
)
blueprint.storage = SQLAlchemyStorage(OAuth, db.session, user=current_user)

container = LocalStorageDriver(config.storage_location).get_container("transcriptions")
StorageManager.add_storage("default", container)


@login_manager.user_loader
def load_user(oauth_id: int):
    return db.session.query(OAuth).filter_by(user_id=int(oauth_id)).one().user


@oauth_authorized.connect_via(blueprint)
def handle_login(blueprint, token):
    if not token:
        # flash("Failed to log in.", ="error")
        return False
    resp = blueprint.session.get("/api/users/@me")
    if not resp.ok:
        # msg = "Failed to fetch user info."
        # flash(msg, category="error")
        return False
    info = resp.json()
    logger.info(info)
    user_id = info["id"]
    query = db.session.query(OAuth).filter_by(
        provider=blueprint.name, provider_user_id=user_id
    )
    try:
        oauth = query.one()
    except NoResultFound:
        oauth = OAuth(provider=blueprint.name, provider_user_id=user_id, token=token)

    if oauth.user:
        logger.info("sadasd")
        _ = login_user(oauth.user)
        # flash("Successfully signed in.")
    else:

        u = Users(
            name=info["global_name"],
            external_account_id=str(info["id"]),
            account_type=AccountSource.Discord,
            avatar_url=f"https://cdn.discordapp.com/avatars/{info["id"]}/{info["avatar"]}.png",
        )
        oauth.user = u
        db.session.add_all([u, oauth])

        db.session.commit()
        _ = login_user(u)
    # Disable Flask-Dance's default behavior for saving the OAuth token
    return False


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

    app.register_blueprint(blueprint, url_prefix="/login")
    return app


app = create_app()
