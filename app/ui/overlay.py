from __future__ import annotations

import math
import queue
import threading
import tkinter as tk
from typing import Sequence


class StatusOverlay:
    """Compact glass HUD compatible with the existing overlay callback API."""

    CARD_W = 520
    CARD_H = 150

    def __init__(self) -> None:
        self._queue: queue.Queue[tuple[str, object, object]] = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="status-overlay", daemon=True)
        self._ready = threading.Event()
        self._root: tk.Tk | None = None
        self._canvas: tk.Canvas | None = None
        self._visible = False
        self._mode = "idle"
        self._text = ""
        self._levels: list[float] = []
        self._phase = 0.0
        self._positioned = False

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()
        self._ready.wait(timeout=5)

    def _run(self) -> None:
        try:
            root = tk.Tk()
        except tk.TclError:
            self._ready.set()
            return
        self._root = root
        root.withdraw()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.94)
        canvas = tk.Canvas(root, width=self.CARD_W, height=self.CARD_H, highlightthickness=0, bg="#050b18")
        canvas.pack()
        self._canvas = canvas
        self._ready.set()
        root.after(80, self._tick)
        root.after(60, self._drain)
        root.mainloop()

    def _drain(self) -> None:
        try:
            while True:
                action, first, second = self._queue.get_nowait()
                if action == "show":
                    self._text, self._mode = str(first or ""), str(second or "idle")
                    self._positioned = False
                    self._visible = True
                elif action == "partial":
                    self._text = str(first)
                    if self._mode not in {"processing", "done", "error"}:
                        self._mode = "recording"
                    self._positioned = False
                    self._visible = True
                elif action == "levels":
                    self._levels = [max(0.0, min(1.0, float(x))) for x in (first or [])]
                elif action == "hide":
                    self._visible = False
                elif action == "quit":
                    if self._root is not None:
                        self._root.destroy()
                    return
        except queue.Empty:
            pass
        if self._root is not None:
            self._root.after(60, self._drain)

    def _tick(self) -> None:
        self._phase += 0.18
        self._draw()
        if self._root is not None:
            self._root.after(80, self._tick)

    def _draw(self) -> None:
        if self._canvas is None:
            return
        c = self._canvas
        c.delete("all")
        if not self._visible:
            self._root.withdraw() if self._root is not None else None
            return
        self._root.deiconify() if self._root is not None else None
        if not self._positioned and self._root is not None:
            self._root.geometry(self._position())
            self._positioned = True
        c.create_rectangle(1, 1, self.CARD_W - 1, self.CARD_H - 1, fill="#0b1a33", outline="#79cfff", width=1)
        c.create_rectangle(12, 12, self.CARD_W - 12, self.CARD_H - 12, fill="#071329", outline="#8bd7ff", width=1)
        c.create_oval(28, 29, 38, 39, fill="#54c7ff", outline="")
        c.create_text(48, 35, text="DICTATION", anchor="w", fill="#72caff", font=("Segoe UI", 13, "bold"))
        c.create_text(self.CARD_W - 28, 35, text=self._mode_label(), anchor="e", fill="#8caec7", font=("Microsoft YaHei UI", 10))
        c.create_line(32, 88, self.CARD_W - 32, 88, fill="#244466")
        points = []
        levels = self._levels or [0.12, 0.22, 0.4, 0.68, 0.34, 0.2, 0.5, 0.75, 0.3, 0.16]
        for index in range(46):
            x = 32 + index * (self.CARD_W - 64) / 45
            level = levels[index % len(levels)]
            y = 88 - math.sin(self._phase + index * 0.72) * (9 + level * 28)
            points.extend((x, y))
        c.create_line(*points, fill="#63d5ff", width=3, smooth=True)
        c.create_text(32, 124, text=self._text[-58:] if self._text else "等待语音输入…", anchor="w", fill="#eaf9ff", font=("Microsoft YaHei UI", 12))
        c.create_text(self.CARD_W - 28, 124, text="燃力AI JAY提供技术支持", anchor="e", fill="#79cfff", font=("Microsoft YaHei UI", 9))

    def _mode_label(self) -> str:
        return {"recording": "录音中", "processing": "识别中", "done": "完成", "error": "出错", "cancelled": "已取消"}.get(self._mode, "就绪")

    def _position(self) -> str:
        if self._root is None:
            return f"{self.CARD_W}x{self.CARD_H}"
        self._root.update_idletasks()
        x = max(0, (self._root.winfo_screenwidth() - self.CARD_W) // 2)
        y = max(0, self._root.winfo_screenheight() - self.CARD_H - 90)
        return f"{self.CARD_W}x{self.CARD_H}+{x}+{y}"

    def show(self, text: str = "", mode: str = "idle") -> None:
        self._queue.put(("show", text, mode))

    def show_partial(self, text: str) -> None:
        self._queue.put(("partial", text, None))

    def set_levels(self, levels: Sequence[float]) -> None:
        self._queue.put(("levels", list(levels), None))

    def hide(self) -> None:
        self._queue.put(("hide", None, None))

    def stop(self) -> None:
        self._queue.put(("quit", None, None))
