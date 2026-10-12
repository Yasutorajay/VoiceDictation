# Source Generated with Decompyle++
# File: logging_setup.pyc (Python 3.12)

from __future__ import annotations
import logging
import sys
from pathlib import Path

def setup_logging(level = None, log_dir = None):
    root = logging.getLogger()
    if root.handlers:
        return None
    numeric = getattr(logging, str(level or "INFO").upper(), logging.INFO)
    root.setLevel(numeric)
    fmt = logging.Formatter('%(asctime)s | %(levelname)-7s | %(name)s | %(message)s', datefmt = '%H:%M:%S')
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)
    if log_dir is not None:
        directory = Path(log_dir)
        directory.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(directory / "app.log", encoding="utf-8")
        handler.setFormatter(fmt)
        root.addHandler(handler)
