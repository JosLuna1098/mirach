"""Logging configuration with rotating file handler and stdout.

File logs rotate at 1 MB with 3 backups. Stdout is used for journalctl
integration when running as a systemd service.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from mirach import config


def setup() -> logging.Logger:
    """Create and configure the 'mirach' logger. Idempotent — safe to call multiple times."""
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("mirach")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    # Rotating file: 1 MB max, keep 3 backups
    fh = RotatingFileHandler(config.LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Stdout for journalctl / interactive debugging
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    return logger


log = setup()
