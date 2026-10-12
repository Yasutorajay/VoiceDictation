from __future__ import annotations

import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

from app.branding import APP_VERSION, BRAND_NAME, COPYRIGHT_NOTICE, OFFICIAL_ACCOUNT_NAME


class AboutWindow:
    def __init__(self, project_root: Path, on_close: Callable[[], None]) -> None:
        self._project_root = project_root
        self._on_close = on_close
        self._thread: threading.Thread | None = None

    def open(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="about", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        root = tk.Tk()
        root.title(f"关于 {BRAND_NAME}")
        root.geometry("560x430")
        root.resizable(False, False)
        frame = ttk.Frame(root, padding=22)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"{BRAND_NAME} {APP_VERSION}", font=("Microsoft YaHei UI", 18, "bold")).pack(anchor="w")
        ttk.Label(frame, text="燃砺AiJay 提供技术支持", foreground="#555555").pack(anchor="w", pady=(2, 18))
        ttk.Label(frame, text="由 RanLiAiJay 自主设计并借助 AI 工具研发", font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w")
        ttk.Label(frame, text=COPYRIGHT_NOTICE, wraplength=510, justify="left").pack(anchor="w", pady=(8, 18))
        ttk.Separator(frame).pack(fill="x", pady=8)
        ttk.Label(frame, text="领取官方下载包", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w")
        ttk.Label(frame, text=f"微信搜索公众号「{OFFICIAL_ACCOUNT_NAME}」", foreground="#0A66C2").pack(anchor="w", pady=(6, 10))

        def copy_account() -> None:
            root.clipboard_clear()
            root.clipboard_append(OFFICIAL_ACCOUNT_NAME)
            root.update()
            messagebox.showinfo("已复制", f"已复制公众号：{OFFICIAL_ACCOUNT_NAME}", parent=root)

        def open_notices() -> None:
            path = self._project_root / "THIRD_PARTY_NOTICES.txt"
            if not path.is_file():
                messagebox.showerror("文件不存在", "未找到第三方许可说明。", parent=root)
                return
            system_root = Path(__import__("os").environ.get("SystemRoot", r"C:\Windows"))
            subprocess.Popen([str(system_root / "System32" / "notepad.exe"), str(path)])

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", side="bottom")
        ttk.Button(buttons, text="复制公众号名称", command=copy_account).pack(side="left")
        ttk.Button(buttons, text="第三方许可", command=open_notices).pack(side="left", padx=8)
        ttk.Button(buttons, text="关闭", command=root.destroy).pack(side="right")
        root.protocol("WM_DELETE_WINDOW", root.destroy)
        try:
            root.mainloop()
        finally:
            self._on_close()
