from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import current_user # type: ignore

# Configure rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["2000 per day", "200 per hour"],
)

# Custom rate limit exemption for authenticated users
def rate_limit_exempt():
    return current_user.is_anonymous == False
