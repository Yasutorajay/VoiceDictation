from __future__ import annotations

import logging
import threading
from typing import Callable

from app.hotkey.keys import NEVER_BLOCK_KEYS, is_mouse_token, normalize_key

logger = logging.getLogger(__name__)


class HotkeyListener:
    """Global keyboard + mouse listener for chord hotkeys.

    Keyboard via `keyboard` package (observe only — never block_key).
    Mouse buttons / horizontal wheel via Win32 WH_MOUSE_LL.

    Critical safety rules:
    - NEVER call keyboard.block_key / suppress=True for modifiers or Enter.
      Those permanently break input when the process dies mid-block.
    - Mouse events used as hotkeys ARE suppressed (return 1) so middle-click
      does not enter auto-scroll mode in the focused app.
    """

    def __init__(
        self,
        on_event: Callable[[str, bool], bool],
        *,
        primary_key: str,
        secondary_key: str,
    ) -> None:
        self._on_event = on_event
        self._primary_key = normalize_key(primary_key)
        self._secondary_key = normalize_key(secondary_key)
        self._kb_hook = None
        self._started = False
        self._lock = threading.Lock()
        self._mouse_hook = None
        self._mouse_thread: threading.Thread | None = None
        self._mouse_stop = threading.Event()
        self._need_mouse = is_mouse_token(self._primary_key) or is_mouse_token(
            self._secondary_key
        )
        self._mouse_proc = None

    def set_bindings(self, primary: str, secondary: str) -> None:
        primary_n = normalize_key(primary)
        secondary_n = normalize_key(secondary)
        need_mouse = is_mouse_token(primary_n) or is_mouse_token(secondary_n)
        with self._lock:
            self._primary_key = primary_n
            self._secondary_key = secondary_n
            if not self._started:
                self._need_mouse = need_mouse
                return
            if need_mouse and self._mouse_hook is None:
                self._start_mouse_hook()
            elif not need_mouse and self._mouse_hook is not None:
                self._stop_mouse_hook()
            self._need_mouse = need_mouse

    def start(self) -> None:
        import keyboard

        with self._lock:
            if self._started:
                return

            def _handler(event) -> None:
                if event.event_type not in ("down", "up"):
                    return
                name = normalize_key(event.name or "")
                if not name:
                    return
                if name == "escape":
                    name = "esc"
                is_down = event.event_type == "down"
                try:
                    self._on_event(name, is_down)
                except Exception:
                    logger.exception("hotkey handler error")

            self._kb_hook = keyboard.hook(_handler, suppress=False)
            self._need_mouse = is_mouse_token(self._primary_key) or is_mouse_token(
                self._secondary_key
            )
            if self._need_mouse:
                self._start_mouse_hook()
            self._started = True
            logger.info(
                "Hotkey listener started (primary=%s secondary=%s mouse=%s)",
                self._primary_key,
                self._secondary_key,
                self._need_mouse,
            )

    def _start_mouse_hook(self) -> None:
        if self._mouse_thread and self._mouse_thread.is_alive():
            return
        self._mouse_stop.clear()
        self._mouse_thread = threading.Thread(
            target=self._mouse_loop, name="mouse-hook", daemon=True
        )
        self._mouse_thread.start()
        logger.info("Mouse hook started")

    def _stop_mouse_hook(self) -> None:
        self._mouse_stop.set()
        try:
            import ctypes

            if self._mouse_thread and self._mouse_thread.native_id:
                ctypes.WinDLL("user32").PostThreadMessageW(
                    self._mouse_thread.native_id, 18, 0, 0
                )
            if self._mouse_thread and self._mouse_thread.is_alive():
                self._mouse_thread.join(timeout=1.5)
            if self._mouse_thread and self._mouse_thread.is_alive():
                logger.error("Mouse hook thread did not stop in time")
                return
            self._mouse_thread = None
            self._mouse_proc = None
            self._mouse_hook = None
            logger.info("Mouse hook stopped")
        except Exception:
            logger.exception("failed to stop mouse hook")

    def _should_suppress_mouse(
        self, token: str, is_down: bool, fsm_wants: bool
    ) -> bool:
        """Suppress middle/side buttons when they are part of the active chord."""
        tok = normalize_key(token)
        if tok not in (self._primary_key, self._secondary_key):
            return False
        return bool(fsm_wants)

    def _mouse_loop(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        WH_MOUSE_LL = 14
        HC_ACTION = 0
        WM_MBUTTONDOWN = 0x0207
        WM_MBUTTONUP = 0x0208
        WM_XBUTTONDOWN = 0x020B
        WM_XBUTTONUP = 0x020C
        WM_MOUSEHWHEEL = 0x020E
        XBUTTON1 = 0x0001
        XBUTTON2 = 0x0002

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

        LowLevelMouseProc = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        user32.SetWindowsHookExW.argtypes = (
            ctypes.c_int,
            LowLevelMouseProc,
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
        user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE

        def _hiword(value: int) -> int:
            return ctypes.c_short((value >> 16) & 0xFFFF).value

        def _dispatch(token: str, is_down: bool) -> bool:
            try:
                return bool(self._on_event(token, is_down))
            except Exception:
                logger.exception("mouse handler error for %s", token)
                return False

        def _callback(nCode: int, wParam: int, lParam: int) -> int:
            suppress = False
            try:
                if nCode == HC_ACTION:
                    info = ctypes.cast(
                        lParam, ctypes.POINTER(MSLLHOOKSTRUCT)
                    ).contents
                    md = int(info.mouseData)
                    token = ""
                    is_down = True
                    if wParam == WM_MBUTTONDOWN:
                        token, is_down = "mouse3", True
                    elif wParam == WM_MBUTTONUP:
                        token, is_down = "mouse3", False
                    elif wParam == WM_XBUTTONDOWN:
                        xb = (md >> 16) & 0xFFFF
                        if xb == XBUTTON1:
                            token, is_down = "mouse4", True
                        elif xb == XBUTTON2:
                            token, is_down = "mouse5", True
                    elif wParam == WM_XBUTTONUP:
                        xb = (md >> 16) & 0xFFFF
                        if xb == XBUTTON1:
                            token, is_down = "mouse4", False
                        elif xb == XBUTTON2:
                            token, is_down = "mouse5", False
                    elif wParam == WM_MOUSEHWHEEL:
                        delta = _hiword(md)
                        token = "wheel_right" if delta > 0 else "wheel_left"
                        is_down = True
                    if token:
                        want = _dispatch(token, is_down)
                        suppress = self._should_suppress_mouse(token, is_down, want)
            except Exception:
                logger.exception("mouse hook callback error")
            if suppress:
                return 1
            return user32.CallNextHookEx(self._mouse_hook, nCode, wParam, lParam)

        self._mouse_proc = LowLevelMouseProc(_callback)
        hook = user32.SetWindowsHookExW(
            WH_MOUSE_LL, self._mouse_proc, kernel32.GetModuleHandleW(None), 0
        )
        self._mouse_hook = hook
        if not hook:
            logger.error("mouse hook failed: %s", ctypes.get_last_error())
            self._mouse_proc = None
            return

        msg = wintypes.MSG()
        try:
            while not self._mouse_stop.is_set():
                has = user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1)
                if has:
                    if msg.message == 0x0012:  # WM_QUIT
                        break
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                else:
                    self._mouse_stop.wait(0.01)
        finally:
            if self._mouse_hook:
                user32.UnhookWindowsHookEx(self._mouse_hook)
            self._mouse_hook = None
            self._mouse_proc = None

    def stop(self) -> None:
        import keyboard

        with self._lock:
            if not self._started:
                return
            self._force_unblock_all()
            try:
                if self._kb_hook is not None:
                    keyboard.unhook(self._kb_hook)
            except Exception:
                try:
                    keyboard.unhook_all()
                except Exception:
                    logger.exception("failed to unhook keyboard")
            self._kb_hook = None
            self._stop_mouse_hook()
            self._started = False
            logger.info("Hotkey listener stopped")

    @staticmethod
    def _force_unblock_all() -> None:
        """Best-effort cleanup of any leftover keyboard.block_key state."""
        try:
            import keyboard

            for name in list(NEVER_BLOCK_KEYS) + [
                "b",
                "a",
                "z",
                "f1",
                "f2",
                "f3",
                "f4",
            ]:
                try:
                    keyboard.unblock_key(name)
                except Exception:
                    pass
            try:
                keyboard.unhook_all()
            except Exception:
                pass
        except Exception:
            pass
