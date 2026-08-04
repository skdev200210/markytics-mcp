from logging.handlers import RotatingFileHandler
from app.core.config import settings

import os
import logging

logger = logging.getLogger("mcp-server")


def configure_logging():
    """Configure the module logger with rotating out/err file handlers and return it (idempotent)."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    os.makedirs(settings.logs_dir, exist_ok=True)

    if logger.handlers:
        logger.setLevel(level)
        return logger

    logger.setLevel(level)
    logger.propagate = False

    out_handler = RotatingFileHandler(
        os.path.join(settings.logs_dir, "app.out.log"),
        maxBytes=20 * 1024 * 1024,
        backupCount=5,
    )
    out_handler.setLevel(level)
    out_handler.setFormatter(formatter)

    err_handler = RotatingFileHandler(
        os.path.join(settings.logs_dir, "app.err.log"),
        maxBytes=20 * 1024 * 1024,
        backupCount=5,
    )
    err_handler.setLevel(logging.WARNING)
    err_handler.setFormatter(formatter)

    logger.addHandler(out_handler)
    logger.addHandler(err_handler)

    return logger


logger = configure_logging()