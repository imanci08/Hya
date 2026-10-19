"""Bounded diagnostic timing records, separate from conversation text."""
from runtime_paths import app_dir
import json
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
import time
import threading

_lock = threading.RLock()
from PySide6.QtCore import QStandardPaths


def _timing(stage, started):
    try:
        logger = logging.getLogger('hya.timings')
        if not logger.handlers:
            path = app_dir('data')/'diagnostics.log'
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(path, os.O_CREAT|os.O_APPEND|os.O_WRONLY|os.O_NOFOLLOW, 0o600)
            os.close(fd)
            handler = RotatingFileHandler(path, maxBytes=256000, backupCount=1)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            logger.propagate = False
        logger.info(json.dumps({'time':time.time(),'stage':stage,'elapsed_ms':round((time.monotonic()-started)*1000,3)}))
    except OSError:
        pass  # Diagnostics never gate actions; the separate action audit does.


def timing(stage, started):
    with _lock:
        _timing(stage, started)
