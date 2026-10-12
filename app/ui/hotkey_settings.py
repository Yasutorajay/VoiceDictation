from __future__ import annotations

import logging
import sys
import threading
import tkinter as tk
from dataclasses import dataclass, replace
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable, Literal
from winreg import (
    CloseKey,
    CreateKey,
    DeleteValue,
    HKEY_CURRENT_USER,
    OpenKey,
    QueryValueEx,
    REG_SZ,
    SetValueEx,
)

from app.config import cleanup_logs, logs_dir, save_user_config_patch, update_runtime_config
from app.hotkey.keys import (
    HOTKEY_CHOICES,
    format_chord,
    label_from_token,
    normalize_key,
    token_from_label,
    validate_hotkey_pair,
)

logger = logging.getLogger(__name__)
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "VoiceDictationRanLiAiJay"
RETENTION_OPTIONS = {"1 天": 1, "3 天": 3, "7 天（推荐）": 7, "30 天": 30, "永不自动删除": None}
PERFORMANCE_OPTIONS = {
    "极速模式（模型全部常驻）": "speed",
    "均衡模式（推荐）": "balanced",
    "低内存模式（首次使用加载）": "low_memory",
}


@dataclass(frozen=True)
class HotkeySelection:
    primary: str
    secondary: str

    def with_capture(self, slot: Literal["primary", "secondary"] | str, token: str) -> "HotkeySelection":
        normalized = normalize_key(token)
        if not normalized:
            return self
        if slot == "primary":
            return replace(self, primary=normalized)
        if slot == "secondary":
            return replace(self, secondary=normalized)
        raise ValueError(f"未知捕获位置：{slot}")


def resolve_hotkey_selection(primary_label: str, secondary_label: str) -> HotkeySelection:
    selection = HotkeySelection(token_from_label(primary_label), token_from_label(secondary_label))
    error = validate_hotkey_pair(selection.primary, selection.secondary)
    if error:
        raise ValueError(error)
    return selection


def performance_settings_patch(
    mode_label: str, live_preview: bool
) -> dict[str, Any]:
    mode = PERFORMANCE_OPTIONS[mode_label]
    return {
        "performance": {"mode": mode},
        "live_preview": {
            "enabled": bool(live_preview) and mode != "low_memory"
        },
        "recording": {
            "save_last_capture": False,
            "save_last_result": False,
        },
    }


def startup_command(executable: Path, script: Path | None = None) -> str:
    command = f'"{executable.absolute()}"'
    return f'{command} "{script.absolute()}"' if script else command


def current_startup_command() -> str:
    executable = Path(sys.executable)
    if getattr(sys, "frozen", False):
        return startup_command(executable)
    return startup_command(executable, Path(__file__).resolve().parents[2] / "main.py")


def startup_value_matches(value: str, expected: str) -> bool:
    return value.strip().casefold() == expected.strip().casefold()


def startup_enabled() -> bool:
    try:
        key = OpenKey(HKEY_CURRENT_USER, RUN_KEY)
        try:
            value, value_type = QueryValueEx(key, RUN_VALUE)
            return value_type == REG_SZ and startup_value_matches(value, current_startup_command())
        finally:
            CloseKey(key)
    except FileNotFoundError:
        return False


def set_startup(enabled: bool) -> None:
    key = CreateKey(HKEY_CURRENT_USER, RUN_KEY)
    try:
        if enabled:
            SetValueEx(key, RUN_VALUE, 0, REG_SZ, current_startup_command())
        else:
            try:
                DeleteValue(key, RUN_VALUE)
            except FileNotFoundError:
                pass
    finally:
        CloseKey(key)


def set_startup_verified(enabled: bool) -> None:
    set_startup(enabled)
    if startup_enabled() != enabled:
        raise OSError("开机自动启动设置未能写入注册表，请检查系统安全软件权限")


class HotkeySettingsWindow:
    def __init__(
        self,
        *,
        primary: str,
        secondary: str,
        on_save: Callable[[str, str], None],
        cfg: dict[str, Any] | None = None,
        on_capture: Callable[[Callable[[str], None]], None] | None = None,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        self._selection = HotkeySelection(normalize_key(primary), normalize_key(secondary))
        self._on_save = on_save
        self._cfg = cfg or {}
        self._on_capture = on_capture
        self._on_close = on_close
        self._root: tk.Tk | None = None
        self._closed = False
        self._opened = False
        self._capture_button: ttk.Button | None = None
        self._capture_slot: str | None = None

    def open(self) -> None:
        if self._opened:
            return
        self._opened = True
        threading.Thread(target=self._run, name="hotkey-settings", daemon=True).start()

    def _run(self) -> None:
        root = tk.Tk()
        self._root = root
        root.title("语音听写设置 · RanLiAiJay")
        root.geometry("640x750")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self._close)

        frame = ttk.Frame(root, padding=24)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="热键设置", font=("Microsoft YaHei UI", 18, "bold")).pack(anchor="w")
        ttk.Label(frame, text="按住主键，再按一次辅助键开始听写。保存后立即生效。", foreground="#555").pack(anchor="w", pady=(4, 18))

        primary_labels = [label for token, label in HOTKEY_CHOICES if validate_hotkey_pair(token, "f12") is None]
        all_labels = [label for _token, label in HOTKEY_CHOICES]
        self._primary_var = tk.StringVar(value=label_from_token(self._selection.primary))
        self._secondary_var = tk.StringVar(value=label_from_token(self._selection.secondary))
        self._status_var = tk.StringVar(value=f"当前：{format_chord(self._selection.primary, self._selection.secondary)}")

        self._add_key_row(frame, "主键", self._primary_var, primary_labels, "primary")
        self._add_key_row(frame, "辅助键", self._secondary_var, all_labels, "secondary")

        settings = ttk.LabelFrame(frame, text="常规", padding=14)
        settings.pack(fill="x", pady=(18, 10))
        logging_cfg = self._cfg.get("logging", {})
        current_retention = logging_cfg.get("retention_days", 7)
        retention_label = next((label for label, days in RETENTION_OPTIONS.items() if days == current_retention), "7 天（推荐）")
        self._retention_var = tk.StringVar(value=retention_label)
        ttk.Label(settings, text="听写历史保留").grid(row=0, column=0, sticky="w")
        ttk.Combobox(settings, textvariable=self._retention_var, values=list(RETENTION_OPTIONS), state="readonly", width=20).grid(row=0, column=1, padx=(24, 0))
        self._startup_var = tk.BooleanVar(value=startup_enabled())
        ttk.Checkbutton(
            settings,
            text="登录 Windows 后自动启动",
            variable=self._startup_var,
            command=self._toggle_startup,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(12, 0))
        sound_enabled = self._cfg.get("branding", {}).get("startup_sound", True)
        self._sound_var = tk.BooleanVar(value=sound_enabled)
        ttk.Checkbutton(settings, text="启动时播放科技感音效", variable=self._sound_var).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        performance = ttk.LabelFrame(frame, text="性能与隐私", padding=14)
        performance.pack(fill="x", pady=(4, 10))
        current_mode = self._cfg.get("performance", {}).get("mode", "balanced")
        mode_label = next(
            (label for label, value in PERFORMANCE_OPTIONS.items() if value == current_mode),
            "均衡模式（推荐）",
        )
        self._performance_var = tk.StringVar(value=mode_label)
        ttk.Label(performance, text="运行模式").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            performance,
            textvariable=self._performance_var,
            values=list(PERFORMANCE_OPTIONS),
            state="readonly",
            width=30,
        ).grid(row=0, column=1, padx=(24, 0), sticky="w")
        self._preview_var = tk.BooleanVar(
            value=bool(self._cfg.get("live_preview", {}).get("enabled", False))
        )
        ttk.Checkbutton(
            performance,
            text="录音时显示实时识别预览（会增加 CPU 占用）",
            variable=self._preview_var,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(12, 0))
        ttk.Label(
            performance,
            text="实时预览保存后立即生效；运行模式将在重启软件后生效。",
            foreground="#777",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))

        ttk.Label(frame, textvariable=self._status_var, foreground="#1769aa", wraplength=540).pack(anchor="w", pady=(12, 8))
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="取消", command=self._close).pack(side="right")
        self._save_button = ttk.Button(buttons, text="保存并立即生效", command=self._save)
        self._save_button.pack(side="right", padx=(0, 10))
        ttk.Label(frame, text="燃砺AiJay 提供技术支持 · 微信公众号：燃砺Ai百宝库", foreground="#777", font=("Microsoft YaHei UI", 9)).pack(side="bottom", pady=(18, 0))
        root.mainloop()

    def _add_key_row(self, parent: ttk.Frame, title: str, variable: tk.StringVar, labels: list[str], slot: str) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=6)
        ttk.Label(row, text=title, width=10).pack(side="left")
        ttk.Combobox(row, textvariable=variable, values=labels, state="readonly", width=29).pack(side="left", padx=(0, 10))
        button = ttk.Button(row, text=f"捕获{title}", command=lambda: self._capture(slot, button))
        button.pack(side="left")

    def _capture(self, slot: str, button: ttk.Button) -> None:
        if self._on_capture is None:
            self._status_var.set("当前版本未启用按键捕获，请使用下拉选择。")
            return
        if self._capture_button is not None and self._capture_button is not button:
            self._restore_capture_button()
        self._capture_button = button
        self._capture_slot = slot
        button.configure(state="disabled", text="请按一个键…")
        self._status_var.set("正在捕获：请按键盘键或支持的鼠标键；按 Esc 取消。")

        def captured(token: str) -> None:
            root = self._root
            if root is not None and not self._closed:
                try:
                    root.after(0, lambda: self._apply_capture(slot, token, button))
                except tk.TclError:
                    logger.debug("Settings window closed before capture result arrived")
            elif not self._closed:
                self._apply_capture(slot, token, button)

        try:
            self._on_capture(captured)
        except Exception as exc:
            self._restore_capture_button()
            self._status_var.set(f"捕获启动失败：{exc}")

    def _apply_capture(self, slot: str, token: str, button: ttk.Button) -> None:
        if button is not self._capture_button or slot != self._capture_slot:
            return
        self._restore_capture_button()
        if not token:
            self._status_var.set("已取消捕获，原热键未改变。")
            return
        try:
            current = HotkeySelection(
                token_from_label(self._primary_var.get()),
                token_from_label(self._secondary_var.get()),
            )
        except (AttributeError, tk.TclError):
            current = self._selection
        candidate = current.with_capture(slot, token)
        error = validate_hotkey_pair(candidate.primary, candidate.secondary)
        if error:
            self._status_var.set(f"该按键不能使用：{error}")
            return
        self._selection = candidate
        self._primary_var.set(label_from_token(candidate.primary))
        self._secondary_var.set(label_from_token(candidate.secondary))
        self._status_var.set(f"已捕获：{label_from_token(token)}；待保存：{format_chord(candidate.primary, candidate.secondary)}")

    def _restore_capture_button(self) -> None:
        button = self._capture_button
        slot = self._capture_slot
        self._capture_button = None
        self._capture_slot = None
        if button is not None and slot is not None:
            button.configure(state="normal", text=f"捕获{'主键' if slot == 'primary' else '辅助键'}")

    def _toggle_startup(self) -> None:
        enabled = bool(self._startup_var.get())
        try:
            set_startup_verified(enabled)
        except Exception as exc:
            logger.exception("Failed to verify startup setting")
            try:
                self._startup_var.set(startup_enabled())
                detail = "已重新读取启动项状态"
            except OSError:
                logger.exception("Failed to read startup state after verification error")
                detail = "启动项状态未知，请重新打开设置检查"
            self._status_var.set(f"开机自动启动设置失败：{exc}；{detail}")
            messagebox.showerror("无法设置开机自动启动", str(exc), parent=self._root)
            return
        state = "已开启并验证" if enabled else "已关闭并验证"
        self._status_var.set(f"开机自动启动{state}")

    def _save(self) -> None:
        self._save_button.configure(state="disabled")
        try:
            selection = resolve_hotkey_selection(self._primary_var.get(), self._secondary_var.get())
            self._on_save(selection.primary, selection.secondary)
            retention = RETENTION_OPTIONS[self._retention_var.get()]
            patch = {
                "logging": {"retention_days": retention},
                "branding": {"startup_sound": self._sound_var.get()},
            }
            patch.update(
                performance_settings_patch(
                    self._performance_var.get(),
                    self._preview_var.get(),
                )
            )
            save_user_config_patch(patch, self._cfg)
            update_runtime_config(self._cfg, patch)
            set_startup_verified(self._startup_var.get())
            if retention is not None:
                cleanup_logs(
                    logs_dir(self._cfg),
                    retention,
                    Path(self._cfg["paths"]["data_dir"]),
                )
            self._selection = selection
            self._status_var.set(
                f"已保存：{format_chord(selection.primary, selection.secondary)}；"
                "热键和实时预览立即生效，启动音效和运行模式重启后生效"
            )
        except Exception as exc:
            logger.exception("Failed to save settings")
            self._status_var.set(f"保存失败：{exc}")
            messagebox.showerror("无法保存设置", str(exc), parent=self._root)
        finally:
            self._save_button.configure(state="normal")

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._root is not None:
            self._root.destroy()
        if self._on_close is not None:
            self._on_close()
