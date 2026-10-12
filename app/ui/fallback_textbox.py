from __future__ import annotations

import threading
import time
import logging
from collections import deque
import tkinter as tk
from tkinter import ttk

import keyboard

logger = logging.getLogger(__name__)

WINDOW_GEOMETRY = "620x435"
WINDOW_MIN_SIZE = (620, 435)
SUPPORT_TEXT = "燃力AiJay 提供技术支持"
PIN_BUTTON_OFF_TEXT = "📌 置顶"
PIN_BUTTON_ON_TEXT = "📌 已置顶"
PIN_STATUS_ON = "已置顶：窗口将保持在其他窗口之上"
PIN_STATUS_OFF = "已取消置顶"
TOP_LIFT_RELEASE_MS = 250


class FallbackTextBox:
    """备用文本窗口：双击 F10 显示/隐藏，注入失败时自动填入识别结果。"""

    def __init__(self) -> None:
        self._root: tk.Tk | None = None
        self._text: tk.Text | None = None
        self._history: deque[tuple[str, bool]] = deque(maxlen=5)
        self._status: tk.StringVar | None = None
        self._thread = threading.Thread(target=self._run, name="fallback-textbox", daemon=True)
        self._ready = threading.Event()
        self._stopped = threading.Event()
        self._last_f10 = 0.0
        self._pinned = False
        self._pin_button: ttk.Button | None = None

    def start_hotkey_listener(self) -> None:
        self._thread.start()
        if not self._ready.wait(timeout=5):
            logger.error("fallback textbox UI thread did not become ready")
        keyboard.on_press_key("f10", self._on_f10, suppress=False)
        keyboard.add_hotkey("ctrl+f10", self.toggle, suppress=False)

    def _run(self) -> None:
        try:
            root = tk.Tk()
        except Exception:
            logger.exception("failed to create fallback textbox window")
            self._ready.set()
            return
        self._root = root
        root.title("VoiceDictation · 文本输入框")
        root.geometry(WINDOW_GEOMETRY)
        root.minsize(*WINDOW_MIN_SIZE)
        root.configure(bg="#08111f")
        root.withdraw()
        root.protocol("WM_DELETE_WINDOW", self.hide)
        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Fallback.TFrame", background="#08111f")
        style.configure("Fallback.TLabel", background="#08111f", foreground="#9ed8ff", font=("Microsoft YaHei UI", 10))
        style.configure("Fallback.TButton", padding=(12, 6), foreground="#08111f")
        style.configure("FallbackPin.TButton", padding=(12, 6), foreground="#08111f")
        style.configure("FallbackPinOn.TButton", padding=(12, 6), foreground="#08111f", background="#FFD60A")
        frame = ttk.Frame(root, style="Fallback.TFrame", padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="VOICE DICTATION  ·  备用文本输入", style="Fallback.TLabel", font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w")
        ttk.Label(frame, text="双击 F10 显示/隐藏；本次结果大字显示，最近五次结果自动保留。", style="Fallback.TLabel").pack(anchor="w", pady=(4, 12))
        self._text = tk.Text(frame, height=10, wrap="word", undo=True, bg="#101d30", fg="#e8f6ff", insertbackground="#7bd7ff", relief="flat", padx=12, pady=10, font=("Microsoft YaHei UI", 12))
        self._text.tag_configure("current", foreground="#f4fbff", font=("Microsoft YaHei UI", 18, "bold"), spacing3=8)
        self._text.tag_configure("history", foreground="#8daac1", font=("Microsoft YaHei UI", 10), spacing3=3)
        self._text.tag_configure("ok", foreground="#77e3ae")
        self._text.tag_configure("failed", foreground="#ff9a9a")
        self._text.pack(fill="both", expand=True)
        bottom = ttk.Frame(frame, style="Fallback.TFrame")
        bottom.pack(fill="x", pady=(12, 0))
        self._status = tk.StringVar(value="就绪")
        ttk.Label(bottom, textvariable=self._status, style="Fallback.TLabel").pack(side="left")
        self._pin_button = ttk.Button(bottom, text=PIN_BUTTON_OFF_TEXT, style="FallbackPin.TButton", command=self._toggle_pin)
        self._pin_button.pack(side="left", padx=(12, 0))
        ttk.Button(bottom, text="复制本次结果", style="Fallback.TButton", command=self._copy).pack(side="right")
        ttk.Button(bottom, text="清空", style="Fallback.TButton", command=self._clear).pack(side="right", padx=(0, 8))
        ttk.Label(frame, text=SUPPORT_TEXT, style="Fallback.TLabel", font=("Microsoft YaHei UI", 9)).pack(anchor="center", pady=(10, 0))
        self._ready.set()
        root.mainloop()

    def _on_f10(self, _event) -> None:
        # Ctrl+F10 由独立热键处理；按住 Ctrl 时不参与双击计数，避免一次按键触发两次切换。
        if keyboard.is_pressed("ctrl") or keyboard.is_pressed("right ctrl"):
            return
        now = time.monotonic()
        if now - self._last_f10 <= 0.45:
            self._last_f10 = 0.0
            self.toggle()
        else:
            self._last_f10 = now

    def toggle(self) -> None:
        if self._root is None:
            return
        try:
            self._root.after(0, self._toggle_ui)
        except tk.TclError:
            logger.debug("fallback toggle skipped: window destroyed")

    def _toggle_ui(self) -> None:
        if self._root is None:
            return
        if self._root.state() == "withdrawn":
            self._root.deiconify()
            self._root.lift()
            self._root.attributes("-topmost", True)
            if not self._pinned:
                self._root.after(TOP_LIFT_RELEASE_MS, self._release_topmost)
            if self._history:
                self._text.focus_set()
        else:
            self._root.withdraw()

    def _toggle_pin(self) -> None:
        """切换窗口置顶：置顶后窗口保持在其他窗口之上，再点一次取消。"""
        if self._root is None:
            return
        self._pinned = not self._pinned
        try:
            self._root.attributes("-topmost", self._pinned)
        except tk.TclError:
            self._pinned = not self._pinned
            logger.debug("fallback pin toggle skipped: window destroyed")
            return
        if self._pin_button is not None:
            self._pin_button.configure(
                text=PIN_BUTTON_ON_TEXT if self._pinned else PIN_BUTTON_OFF_TEXT,
                style="FallbackPinOn.TButton" if self._pinned else "FallbackPin.TButton",
            )
        if self._status is not None:
            self._status.set(PIN_STATUS_ON if self._pinned else PIN_STATUS_OFF)

    def _release_topmost(self) -> None:
        """弹出提示期结束后取消临时置顶；用户已钉住时保持置顶。"""
        if self._root is None or self._pinned:
            return
        try:
            self._root.attributes("-topmost", False)
        except tk.TclError:
            logger.debug("fallback topmost release skipped: window destroyed")

    def hide(self) -> None:
        if self._root is None:
            return
        try:
            self._root.after(0, self._root.withdraw)
        except tk.TclError:
            logger.debug("fallback hide skipped: window destroyed")

    def set_text(self, text: str, error: str | None = None) -> None:
        if self._root is None:
            return
        def update() -> None:
            self._history.append((text, error is not None))
            self._render()
            if self._status is not None:
                self._status.set("本次注入失败，已保留文本" if error else "本次注入成功 · 已保留最近五次结果")
        try:
            self._root.after(0, update)
        except tk.TclError:
            logger.debug("fallback set_text skipped: window destroyed")

    @staticmethod
    def _shorten(text: str, limit: int = 180) -> str:
        compact = " ".join(text.split())
        return compact if len(compact) <= limit else compact[: limit - 1] + "…"

    def _render(self) -> None:
        if self._text is None:
            return
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        if not self._history:
            self._text.insert("end", "等待下一次语音输入…", "history")
        else:
            current, failed = self._history[-1]
            self._text.insert("end", "本次结果\n", "history")
            self._text.insert("end", current, "current")
            self._text.insert("end", "\n" + ("⚠ 注入失败 · 可复制手动粘贴" if failed else "✓ 已尝试注入"), "failed" if failed else "ok")
            previous = list(self._history)[:-1]
            if previous:
                self._text.insert("end", "\n\n最近结果\n", "history")
                for index, (item, item_failed) in enumerate(reversed(previous), 1):
                    marker = "失败" if item_failed else "成功"
                    self._text.insert("end", f"{index}. [{marker}] {self._shorten(item)}\n", "history")
        self._text.configure(state="disabled")

    def _copy(self) -> None:
        if self._root is not None and self._history:
            self._root.clipboard_clear()
            self._root.clipboard_append(self._history[-1][0])
            if self._status is not None:
                self._status.set("已复制本次识别文本")

    def _clear(self) -> None:
        if self._text is not None:
            self._text.configure(state="normal")
            self._text.delete("1.0", "end")
            self._text.configure(state="disabled")
            self._history.clear()
            if self._status is not None:
                self._status.set("已清空")

    def stop(self) -> None:
        keyboard.unhook_all()
        self._stopped.set()
        if self._root is not None:
            try:
                self._root.after(0, self._root.destroy)
            except tk.TclError:
                logger.debug("fallback destroy skipped: window already destroyed")
        if self._thread.is_alive():
            self._thread.join(timeout=3)
