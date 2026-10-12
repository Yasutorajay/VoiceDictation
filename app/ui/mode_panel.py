from __future__ import annotations

import tkinter as tk
import threading
from tkinter import ttk
from typing import Callable

from app.postprocess.modes import MODES


class ModePanel:
    def __init__(self, on_mode: Callable[[str], None]) -> None:
        self._on_mode = on_mode
        self._root: tk.Tk | None = None
        self._visible = True

    def start(self) -> None:
        threading.Thread(target=self._run, name="mode-panel", daemon=True).start()

    def _run(self) -> None:
        root = tk.Tk()
        self._root = root
        self._ready.set() if hasattr(self, "_ready") else None
        root.title("VoiceDictation")
        root.geometry("190x88-24-72")
        root.resizable(False, False)
        root.configure(bg="#08111f")
        root.attributes("-topmost", True)
        root.protocol("WM_DELETE_WINDOW", self.hide)
        frame = tk.Frame(root, bg="#08111f", highlightbackground="#1769aa", highlightthickness=1)
        frame.pack(fill="both", expand=True, padx=2, pady=2)
        tk.Label(frame, text="VOICE  ·  模式", bg="#08111f", fg="#9ed8ff", font=("Microsoft YaHei UI", 9, "bold")).pack(anchor="w", padx=8, pady=(5, 1))
        selected = tk.StringVar(value=MODES[1])
        box = ttk.Combobox(frame, textvariable=selected, values=MODES, state="readonly", width=15)
        box.pack(fill="x", padx=8, pady=(1, 3))
        box.bind("<<ComboboxSelected>>", lambda _e: self._on_mode(selected.get()))
        tk.Label(frame, text="Ctrl+F10 显示/隐藏 · 燃力AiJay", bg="#08111f", fg="#7291a8", font=("Microsoft YaHei UI", 8)).pack(anchor="w", padx=8)
        root.mainloop()

    def show(self) -> None:
        if self._root:
            self._visible = True
            self._root.after(0, self._root.deiconify)

    def hide(self) -> None:
        if self._root:
            self._visible = False
            self._root.after(0, self._root.withdraw)

    def toggle(self) -> None:
        (self.hide if self._visible else self.show)()

    def stop(self) -> None:
        if self._root:
            self._root.after(0, self._root.destroy)
