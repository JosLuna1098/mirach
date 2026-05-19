"""Logging with file rotation + stdout (for journalctl)."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from mirach import config


def setup() -> logging.Logger:
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("mirach")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    fh = RotatingFileHandler(config.LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    return logger


log = setup()
