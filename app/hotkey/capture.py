from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes
from typing import Callable

from app.hotkey.keys import normalize_key

logger = logging.getLogger(__name__)

WM_MBUTTONDOWN = 0x0207
WM_XBUTTONDOWN = 0x020B
WM_MOUSEHWHEEL = 0x020E
XBUTTON1 = 0x0001
XBUTTON2 = 0x0002


def _hiword(value: int) -> int:
    return ctypes.c_short((value >> 16) & 0xFFFF).value


def token_from_mouse_message(message: int, mouse_data: int) -> str:
    if message == WM_MBUTTONDOWN:
        return "mouse3"
    if message == WM_XBUTTONDOWN:
        button = (mouse_data >> 16) & 0xFFFF
        if button == XBUTTON1:
            return "mouse4"
        if button == XBUTTON2:
            return "mouse5"
    if message == WM_MOUSEHWHEEL:
        return "wheel_right" if _hiword(mouse_data) > 0 else "wheel_left"
    return ""


class OneShotHotkeyCapture:
    def __init__(self, callback: Callable[[str], None]) -> None:
        self._callback = callback
        self._done = threading.Event()
        self._complete_lock = threading.Lock()
        self._keyboard_hook = None
        self._mouse_thread: threading.Thread | None = None
        self._mouse_thread_id: int | None = None

    def start(self) -> None:
        import keyboard

        def on_keyboard(event: keyboard.KeyboardEvent) -> None:
            if event.event_type != "down":
                return
            token = normalize_key(event.name or "")
            if token in ("esc", "escape"):
                self._complete("")
            elif token:
                self._complete(token)

        self._keyboard_hook = keyboard.hook(on_keyboard, suppress=False)
        self._mouse_thread = threading.Thread(
            target=self._mouse_loop,
            name="hotkey-capture-mouse",
            daemon=True,
        )
        self._mouse_thread.start()

    def cancel(self) -> None:
        with self._complete_lock:
            self._done.set()
        self._unhook_keyboard()
        if self._mouse_thread_id:
            ctypes.WinDLL("user32").PostThreadMessageW(
                self._mouse_thread_id, 0x0012, 0, 0
            )

    def _complete(self, token: str) -> None:
        with self._complete_lock:
            if self._done.is_set():
                return
            self._done.set()
        self._unhook_keyboard()
        self._callback(token)

    def _unhook_keyboard(self) -> None:
        if self._keyboard_hook is None:
            return
        try:
            import keyboard

            keyboard.unhook(self._keyboard_hook)
        except Exception:
            logger.exception("failed to stop capture keyboard hook")
        self._keyboard_hook = None

    def _mouse_loop(self) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._mouse_thread_id = kernel32.GetCurrentThreadId()

        class POINT(ctypes.Structure):
            _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

        class MSLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [
                ("pt", POINT),
                ("mouseData", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t),
            ]

        proc_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        user32.SetWindowsHookExW.argtypes = (
            ctypes.c_int,
            proc_type,
            wintypes.HINSTANCE,
            wintypes.DWORD,
        )
        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        user32.CallNextHookEx.restype = ctypes.c_ssize_t
        user32.CallNextHookEx.argtypes = (
            wintypes.HHOOK,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE

        def callback(code: int, message: int, data: int) -> int:
            if code == 0:
                info = ctypes.cast(
                    data, ctypes.POINTER(MSLLHOOKSTRUCT)
                ).contents
                token = token_from_mouse_message(message, int(info.mouseData))
                if token:
                    self._complete(token)
            return user32.CallNextHookEx(hook, code, message, data)

        proc = proc_type(callback)
        hook = user32.SetWindowsHookExW(
            14, proc, kernel32.GetModuleHandleW(None), 0
        )
        if not hook:
            logger.error("capture mouse hook failed: %s", ctypes.get_last_error())
            self._mouse_thread_id = None
            return
        msg = wintypes.MSG()
        try:
            while not self._done.is_set():
                if user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):
                    if msg.message == 0x0012:
                        break
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                else:
                    self._done.wait(0.01)
        finally:
            user32.UnhookWindowsHookEx(hook)
            self._mouse_thread_id = None
