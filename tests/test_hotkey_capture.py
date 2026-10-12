from __future__ import annotations

import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.hotkey.capture import OneShotHotkeyCapture, token_from_mouse_message
from app.hotkey.keys import validate_hotkey_pair


def test_capture_maps_supported_mouse_messages() -> None:
    assert token_from_mouse_message(0x0207, 0) == "mouse3"
    assert token_from_mouse_message(0x020B, 0x00010000) == "mouse4"
    assert token_from_mouse_message(0x020B, 0x00020000) == "mouse5"
    assert token_from_mouse_message(0x020E, 0x00780000) == "wheel_right"
    assert token_from_mouse_message(0x020E, 0xFF880000) == "wheel_left"


def test_capture_ignores_mouse_release_and_unknown_messages() -> None:
    assert token_from_mouse_message(0x0208, 0) == ""
    assert token_from_mouse_message(0x020C, 0x00010000) == ""
    assert token_from_mouse_message(0x0201, 0) == ""


def test_capture_callback_runs_once_under_competing_inputs() -> None:
    captured: list[str] = []
    capture = OneShotHotkeyCapture(captured.append)
    threads = [
        threading.Thread(target=capture._complete, args=(token,))
        for token in ("a", "mouse3")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(captured) == 1


def test_pulse_mouse_token_cannot_be_primary() -> None:
    assert validate_hotkey_pair("wheel_left", "a") is not None
    assert validate_hotkey_pair("mouse3", "right alt") is not None
    assert validate_hotkey_pair("right alt", "mouse3") is None
