import logging
from flask_dance.contrib.discord import make_discord_blueprint # type: ignore
from flask_dance.consumer.storage.sqla import SQLAlchemyStorage # type: ignore
from flask_dance.consumer import oauth_authorized # type: ignore
from flask_login import current_user, login_user # type: ignore
from ..models.db import db, OAuth, Users, AccountSource
from ..models.config import config
from sqlalchemy.exc import NoResultFound
from datetime import timedelta

logger = logging.getLogger(__name__)

blueprint = make_discord_blueprint(
    client_id=config.discord_client_id,
    client_secret=config.discord_client_secret,
    scope=["identify"],
    storage=SQLAlchemyStorage(OAuth, db.session, user=current_user)
)

@oauth_authorized.connect_via(blueprint)
def handle_login(blueprint, token):
    if not token:
        return False
    resp = blueprint.session.get("/api/users/@me")
    if not resp.ok:
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
        _ = login_user(oauth.user, remember=True, duration=timedelta(days=30))
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
        _ = login_user(u, remember=True, duration=timedelta(days=30))
    # Disable Flask-Dance's default behavior for saving the OAuth token
    return False