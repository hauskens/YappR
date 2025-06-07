from app.models.config import config
import logging
from loki_logger_handler.loki_logger_handler import LokiLoggerHandler
from os import getenv

logger = logging.getLogger("custom_logger")

custom_handler = LokiLoggerHandler(
    url=config.loki_url,
    labels={"application": "yappr", "environment": config.environment, "service": config.service_name, "version": getenv("VERSION", "unknown")},
    label_keys={},
    enable_structured_loki_metadata=True,
    timeout=10,
)
logger.addHandler(custom_handler)