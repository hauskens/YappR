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
    
    # First check if a user with this external account ID already exists
    existing_user = db.session.query(Users).filter_by(
        external_account_id=str(user_id),
        account_type=AccountSource.Discord
    ).first()
    
    # Then check for OAuth record
    query = db.session.query(OAuth).filter_by(
        provider=blueprint.name, provider_user_id=user_id
    )
    
    try:
        oauth = query.one()
        # Update the token
        oauth.token = token
    except NoResultFound:
        oauth = OAuth(provider=blueprint.name, provider_user_id=user_id, token=token)

    if oauth.user:
        # Update user info if needed
        if info.get("global_name") and oauth.user.name != info["global_name"]:
            oauth.user.name = info["global_name"]
        if info.get("avatar"):
            avatar_url = f"https://cdn.discordapp.com/avatars/{info['id']}/{info['avatar']}.png"
            if oauth.user.avatar_url != avatar_url:
                oauth.user.avatar_url = avatar_url
        oauth.user.last_login = db.func.now()
        db.session.commit()
        _ = login_user(oauth.user, remember=True, duration=timedelta(days=30))
    elif existing_user:
        # Link existing user to this OAuth
        oauth.user = existing_user
        existing_user.last_login = db.func.now()
        db.session.add(oauth)
        db.session.commit()
        _ = login_user(existing_user, remember=True, duration=timedelta(days=30))
    else:
        # Create new user
        u = Users(
            name=info.get("global_name") or info.get("username") or "Discord User",
            external_account_id=str(info["id"]),
            account_type=AccountSource.Discord,
            avatar_url=f"https://cdn.discordapp.com/avatars/{info['id']}/{info['avatar']}.png" if info.get("avatar") else None,
            first_login=db.func.now(),
            last_login=db.func.now()
        )
        oauth.user = u
        db.session.add_all([u, oauth])
        db.session.commit()
        _ = login_user(u, remember=True, duration=timedelta(days=30))
    
    # Disable Flask-Dance's default behavior for saving the OAuth token
    return False