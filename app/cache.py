from flask_caching import Cache
from app.models.config import config
from flask_login import current_user # type: ignore
from flask import request

def make_cache_key(*args, **kwargs) -> str:
    return f"{current_user.get_id()}:{request.path}:{request.method}:{str(args)}:{str(kwargs)}"

cache = Cache(config={'CACHE_TYPE': 'RedisCache', 'CACHE_KEY_PREFIX': 'cache_', 'CACHE_REDIS_URL': config.redis_uri})