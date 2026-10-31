import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional


def setup_logger(name: str = "MusicBot", level: str = "INFO") -> logging.Logger:
    """
    Sets up a structured, colorized logger for terminal output and writes to a rotating log file.
    """
    logger = logging.getLogger(name)
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)

    # Avoid adding duplicate handlers if logger was already initialized
    if logger.handlers:
        return logger

    # Ensure logs directory exists
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    # File Handler with rotation (10 MB per file, keeps 5 backups)
    file_handler = RotatingFileHandler(
        filename=os.path.join(log_dir, "bot.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_format = logging.Formatter(
        "[%(asctime)s] [%(levelname)-8s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_format)
    file_handler.setLevel(log_level)
    logger.addHandler(file_handler)

    # Console Stream Handler with color support
    console_handler = logging.StreamHandler()
    try:
        import colorlog
        color_format = colorlog.ColoredFormatter(
            "%(log_color)s[%(asctime)s] [%(levelname)-8s]%(reset)s %(cyan)s%(name)s:%(reset)s %(message)s",
            datefmt="%H:%M:%S",
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            }
        )
        console_handler.setFormatter(color_format)
    except ImportError:
        console_format = logging.Formatter(
            "[%(asctime)s] [%(levelname)-8s] %(name)s: %(message)s",
            datefmt="%H:%M:%S"
        )
        console_handler.setFormatter(console_format)

    console_handler.setLevel(log_level)
    logger.addHandler(console_handler)

    return logger

