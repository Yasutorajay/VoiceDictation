from __future__ import annotations

import ctypes
import logging
import time
from contextlib import nullcontext
from ctypes import wintypes
from typing import Any, Callable, ContextManager

import pyperclip

logger = logging.getLogger(__name__)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 2
KEYEVENTF_UNICODE = 4
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_INSERT = 0x2D
VK_V = 0x56

user32 = ctypes.WinDLL("user32", use_last_error=True)


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = wintypes.SHORT
user32.GetForegroundWindow.restype = wintypes.HWND


def _key(vk: int, *, up: bool = False) -> INPUT:
    return INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, 0))


def _unicode_key(unit: int, *, up: bool = False) -> INPUT:
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
    return INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, unit, flags, 0, 0))


def _send(events: list[INPUT]) -> tuple[int, int]:
    values = (INPUT * len(events))(*events)
    sent = int(user32.SendInput(len(values), values, ctypes.sizeof(INPUT)))
    return sent, ctypes.get_last_error() if sent == 0 else 0


def _release_modifiers() -> None:
    modifiers = (VK_CONTROL, VK_SHIFT, VK_MENU, VK_LWIN, VK_RWIN)
    pressed = [vk for vk in modifiers if user32.GetAsyncKeyState(vk) & 0x8000]
    if pressed:
        _send([_key(vk, up=True) for vk in pressed])


def _send_paste(shortcut: str) -> tuple[int, int]:
    modifier, key = (VK_SHIFT, VK_INSERT) if shortcut == "shift_insert" else (VK_CONTROL, VK_V)
    return _send([_key(modifier), _key(key), _key(key, up=True), _key(modifier, up=True)])


def _foreground_window() -> int:
    return int(user32.GetForegroundWindow() or 0)


def capture_target_window() -> int:
    return _foreground_window()


def _type_unicode(text: str) -> tuple[int, int]:
    units = text.encode("utf-16-le")
    events: list[INPUT] = []
    for index in range(0, len(units), 2):
        unit = int.from_bytes(units[index:index + 2], "little")
        events.extend((_unicode_key(unit), _unicode_key(unit, up=True)))
    return _send(events)


def _restore_clipboard_if_unchanged(expected: str, previous: str) -> None:
    try:
        if pyperclip.paste() != expected:
            logger.info("clipboard changed after paste; skip restore")
            return
        pyperclip.copy(previous)
    except Exception:
        logger.warning("clipboard restore failed after successful input")


def inject_text(
    text: str,
    cfg: dict[str, Any],
    *,
    target_window: int | None = None,
    cancelled: Callable[[], bool] | None = None,
    input_gate: ContextManager[None] | None = None,
) -> dict[str, Any]:
    if not text:
        return {"ok": True, "method": "none", "error": None}
    is_cancelled = cancelled or (lambda: False)
    if is_cancelled():
        return {"ok": False, "method": "clipboard_only", "error": "cancelled"}
    if target_window is not None and (
        not target_window or _foreground_window() != target_window
    ):
        return {"ok": False, "method": "clipboard_only", "error": "focus_changed"}
    options = cfg.get("inject", {})
    pre_delay = max(0, int(options.get("pre_paste_delay_ms", 80))) / 1000
    post_delay = max(0, int(options.get("post_paste_delay_ms", 160))) / 1000
    shortcut = str(options.get("paste_shortcut", "ctrl_v"))
    restore = bool(options.get("restore_clipboard", True))
    keep_on_failure = bool(options.get("keep_on_failure", True))
    old_clipboard: str | None = None
    try:
        old_clipboard = pyperclip.paste()
    except Exception:
        logger.warning("failed to snapshot clipboard")
    target_window = target_window or _foreground_window()
    try:
        pyperclip.copy(text)
        _release_modifiers()
        time.sleep(pre_delay)
        with input_gate or nullcontext():
            if is_cancelled():
                raise RuntimeError("cancelled")
            if not target_window or _foreground_window() != target_window:
                raise RuntimeError("focus_changed")
            sent, winerror = _send_paste(shortcut)
        time.sleep(post_delay)
        if sent == 4:
            logger.info("system paste sent shortcut=%s chars=%d", shortcut, len(text))
            if restore and old_clipboard is not None:
                _restore_clipboard_if_unchanged(text, old_clipboard)
            return {"ok": True, "method": shortcut, "error": None}
    except Exception as exc:
        logger.exception("system paste failed")
        paste_error = str(exc)
    else:
        paste_error = f"SendInput sent {sent}/4 events (winerror={winerror})"
    try:
        unicode_result: tuple[int, int] | None = None
        with input_gate or nullcontext():
            if is_cancelled():
                paste_error = f"{paste_error}; cancelled"
            elif not target_window or _foreground_window() != target_window:
                paste_error = f"{paste_error}; focus_changed"
            elif "focus_changed" not in paste_error and bool(options.get("unicode_fallback", True)):
                _release_modifiers()
                unicode_result = _type_unicode(text)
        if unicode_result is not None:
            sent, winerror = unicode_result
            if sent == len(text.encode("utf-16-le")):
                if restore and old_clipboard is not None:
                    _restore_clipboard_if_unchanged(text, old_clipboard)
                return {"ok": True, "method": "unicode", "error": None}
            paste_error = f"{paste_error}; unicode sent {sent} events (winerror={winerror})"
    except Exception as exc:
        paste_error = f"{paste_error}; unicode:{exc}"
    try:
        safe_abort = "focus_changed" in paste_error or "cancelled" in paste_error
        if safe_abort and old_clipboard is not None:
            _restore_clipboard_if_unchanged(text, old_clipboard)
        elif keep_on_failure:
            pyperclip.copy(text)
        elif old_clipboard is not None:
            pyperclip.copy(old_clipboard)
    except Exception as exc:
        paste_error = f"{paste_error}; clipboard_fallback:{exc}"
    return {"ok": False, "method": "clipboard_only", "error": paste_error}
