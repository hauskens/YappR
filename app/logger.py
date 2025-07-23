import logging
from loki_logger_handler.loki_logger_handler import LokiLoggerHandler  # type: ignore
import contextvars
from .models.config import config
from flask import has_request_context, request, g
from flask_login import current_user  # type: ignore
import os
_in_filter_flag = contextvars.ContextVar("_in_filter_flag", default=False)


# Create a custom filter to add user information when available
class UserContextFilter(logging.Filter):
    def filter(self, record):
        # Prevent recursion
        if _in_filter_flag.get():
            return True

        # Set flag to indicate we're in the filter function
        token = _in_filter_flag.set(True)
        try:
            # Only attempt to access Flask context if we're in a request
            if has_request_context():
                # Add request info
                record.method = request.method
                record.path = request.path
                record.remote_addr = request.remote_addr
                if request.is_json:
                    record.body = request.get_data(cache=True, as_text=True)

                # Add request ID if available in g
                if hasattr(g, 'request_id'):
                    record.request_id = g.request_id

                # Safely check if user is authenticated without triggering recursion
                try:
                    if hasattr(current_user, '_get_current_object'):
                        user_obj = current_user._get_current_object()
                        if hasattr(user_obj, 'is_authenticated') and user_obj.is_authenticated:
                            record.user_id = str(user_obj.id) if hasattr(
                                user_obj, 'id') else "unknown_id"
                            record.username = user_obj.name if hasattr(
                                user_obj, 'name') else "unknown_name"
                        elif hasattr(user_obj, 'is_anonymous') and user_obj.is_anonymous:
                            record.user_id = "anonymous"
                            record.username = "anonymous"
                except Exception:
                    # If anything goes wrong, just use default values
                    pass
        finally:
            # Reset the flag
            _in_filter_flag.reset(token)

        return True


# Configure the logger
logger = logging.getLogger("custom_logger")
logger.setLevel(logging.INFO)

if config.debug:
    logger.addHandler(logging.StreamHandler())

# Add our custom filter
user_filter = UserContextFilter()
logger.addFilter(user_filter)

# Add Loki handler if Loki URL is provided
if config.loki_url:
    custom_handler = LokiLoggerHandler(
        url=config.loki_url,
        labels={
            "application": "yappr",
            "environment": config.environment,
            "service": config.service_name,
            "version": os.getenv("VERSION", "unknown")
        },
        label_keys={},
        enable_structured_loki_metadata=True,
        timeout=10,
    )
    logger.addHandler(custom_handler)
