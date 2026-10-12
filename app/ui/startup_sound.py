from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def play_startup_sound(resource_path: Path) -> bool:
    if os.name != "nt" or not resource_path.is_file():
        return False
    try:
        import winsound

        winsound.PlaySound(
            str(resource_path),
            winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
        )
        return True
    except (OSError, RuntimeError, ImportError):
        logger.warning("Startup sound unavailable", exc_info=True)
        return False
