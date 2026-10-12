from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.hotkey.listener import HotkeyListener


def test_listener_does_not_override_fsm_for_idle_middle_click() -> None:
    listener = HotkeyListener(
        lambda _token, _is_down: False,
        primary_key="right alt",
        secondary_key="mouse3",
    )

    assert listener._should_suppress_mouse("mouse3", True, False) is False
    assert listener._should_suppress_mouse("mouse3", False, False) is False
