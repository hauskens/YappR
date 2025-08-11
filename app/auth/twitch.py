
from flask_dance.contrib.twitch import make_twitch_blueprint  # type: ignore
from flask_dance.consumer.storage.sqla import SQLAlchemyStorage  # type: ignore
from flask_dance.consumer import oauth_authorized  # type: ignore
from flask_login import current_user, login_user  # type: ignore
from ..models import db
from ..models.auth import OAuth
from ..models.user import Users
from ..models.enums import AccountSource
from ..models.config import config
from sqlalchemy.exc import NoResultFound
from datetime import timedelta
from app.logger import logger
from twitchAPI.twitch import AuthScope

user_oauth_scope=[AuthScope.USER_READ_MODERATED_CHANNELS]
bot_oauth_scope=[AuthScope.CHAT_READ, AuthScope.CHAT_EDIT, AuthScope.CLIPS_EDIT, AuthScope.USER_BOT]

blueprint = make_twitch_blueprint(
    client_id=config.twitch_client_id,
    client_secret=config.twitch_client_secret,
    scope=user_oauth_scope,
    storage=SQLAlchemyStorage(OAuth, db.session, user=current_user)
)


@oauth_authorized.connect_via(blueprint)
def handle_login(blueprint, token):
    if not token:
        return False
    resp = blueprint.session.get('https://api.twitch.tv/helix/users')
    if not resp.ok:
        return False
    info = resp.json()
    logger.info(info)
    user_id = info["data"][0]["id"]
    query = db.session.query(OAuth).filter_by(
        provider=blueprint.name, provider_user_id=user_id
    )
    try:
        oauth = query.one()
    except NoResultFound:
        oauth = OAuth(provider=blueprint.name,
                      provider_user_id=user_id, token=token)

    if oauth.user:
        _ = login_user(oauth.user, remember=True, duration=timedelta(days=30))
    else:

        logger.info(
            f"checking for existing user with id: {info['data'][0]['id']}")
        existing_user = db.session.query(Users).filter_by(
            external_account_id=str(info["data"][0]["id"])
        ).one_or_none()
        logger.info(f"existing_user: {existing_user}")
        if existing_user is None:
            u = Users(
                name=info["data"][0]["display_name"],
                external_account_id=str(info["data"][0]["id"]),
                account_type=AccountSource.Twitch,
                avatar_url=info["data"][0]["profile_image_url"],
            )
            oauth.user = u
            db.session.add_all([u, oauth])
            db.session.commit()
            _ = login_user(u, remember=True, duration=timedelta(days=30))
        else:
            logger.info(
                f"User {existing_user.name} already exists, logging in")
            oauth.user = existing_user
            db.session.add(oauth)
            db.session.commit()
            _ = login_user(existing_user, remember=True,
                           duration=timedelta(days=30))
    # Disable Flask-Dance's default behavior for saving the OAuth token
    return False


blueprint_bot = make_twitch_blueprint(
    client_id=config.twitch_client_id,
    client_secret=config.twitch_client_secret,
    scope=[scope.value for scope in bot_oauth_scope],
    storage=SQLAlchemyStorage(OAuth, db.session, user=current_user),
)


@oauth_authorized.connect_via(blueprint_bot)
def handle_login_bot(blueprint, token):
    if not token:
        return False
    resp = blueprint.session.get('https://api.twitch.tv/helix/users')
    if not resp.ok:
        return False
    info = resp.json()
    logger.info(f'Bot info: {info}')
    user_id = info["data"][0]["id"]
    query = db.session.query(OAuth).filter_by(
        provider='twitch_bot'
    )
    try:
        oauth = query.one()
    except NoResultFound:
        oauth = OAuth(provider='twitch_bot',
                      provider_user_id=user_id, token=token)

    try:
        query = db.session.query(Users).filter_by(
            name="bot", account_type=AccountSource.Twitch
        )
        u = query.one()
    except NoResultFound:
        u = Users(
            name="bot",
            external_account_id=str(info["data"][0]["id"]),
            account_type=AccountSource.Twitch,
            avatar_url=info["data"][0]["profile_image_url"],
        )
    oauth.user = u
    db.session.add_all([u, oauth])
    db.session.commit()
    # Disable Flask-Dance's default behavior for saving the OAuth token
    return False
