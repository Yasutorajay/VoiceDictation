from __future__ import annotations

import logging
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw

from app.config import load_config, save_user_config_patch
from app.dictionary_manager import DictionaryManager
from app.ui.dictionary_window import DictionaryWindow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LanguageRuleOption:
    key: str
    label: str
    decoder_language: str


LANGUAGE_RULE_OPTIONS = (
    LanguageRuleOption("zh", "中文为主", "zh"),
    LanguageRuleOption("en", "英文为主", "en"),
    LanguageRuleOption("mixed", "中英文混合", "auto"),
)
_LANGUAGE_RULE_BY_KEY = {option.key: option for option in LANGUAGE_RULE_OPTIONS}


def resolve_language_rule(config: dict) -> str:
    configured = str(config.get("postprocess", {}).get("language_rule") or "").strip()
    if configured in _LANGUAGE_RULE_BY_KEY:
        return configured
    decoder_language = str(config.get("asr", {}).get("language") or "auto").strip()
    if decoder_language in {"zh", "en"}:
        return decoder_language
    return "mixed"


def language_settings_patch(rule: str) -> dict:
    try:
        option = _LANGUAGE_RULE_BY_KEY[rule]
    except KeyError as exc:
        raise ValueError(f"未知输入语言规则：{rule}") from exc
    return {
        "asr": {"language": option.decoder_language},
        "postprocess": {"language_rule": option.key},
    }


def runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _make_icon(color: str = "#2563EB", size: int = 64) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = size // 8
    draw.ellipse((margin, margin, size - margin, size - margin), fill=color)
    return image


def _load_icon(color: str = "#2563EB", size: int = 64) -> Image.Image:
    roots = [Path(__file__).resolve().parents[2], Path(sys.executable).resolve().parent]
    if getattr(sys, "_MEIPASS", None):
        roots.append(Path(sys._MEIPASS))
    resource = None
    try:
        resource = next(
            (
                root / "resources" / "VoiceDictation.ico"
                for root in roots
                if (root / "resources" / "VoiceDictation.ico").is_file()
            ),
            None,
        )
        if resource is not None:
            with Image.open(resource) as source:
                source.load()
                icon = source.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
                pixels = icon.load()
                for y in range(size):
                    for x in range(size):
                        red, green, blue, alpha = pixels[x, y]
                        pixels[x, y] = (37, 99, 235, alpha) if red > 220 and green > 220 and blue > 220 else (0, 0, 0, 0)
                return icon
    except Exception:
        logger.exception("failed to load tray icon resource: %s", resource)
    return _make_icon(color, size)


class TrayApp:
    COLORS = {"idle": "#2563EB", "recording": "#DC2626", "processing": "#D97706", "paused": "#6B7280", "error": "#7F1D1D"}

    def __init__(self, *, on_quit: Callable[[], None], on_toggle_pause: Callable[[], None], on_open_logs: Callable[[], None] | None = None, on_open_hotkey_settings: Callable[[], None] | None = None, on_open_about: Callable[[], None] | None = None, chord_label: str = "Right Alt + Mouse Middle", language_rule: str | None = None) -> None:
        self._on_quit = on_quit
        self._on_toggle_pause = on_toggle_pause
        self._on_open_logs = on_open_logs
        self._on_open_hotkey_settings = on_open_hotkey_settings
        self._on_open_about = on_open_about
        self._chord_label = chord_label
        self._icon = None
        self._state = "idle"
        self._paused = False
        self._dictionary_window: DictionaryWindow | None = None
        self._language_rule = language_rule or self._load_language_rule()

    def start(self) -> None:
        threading.Thread(target=self._run, name="tray", daemon=True).start()

    def _open_dictionary(self) -> None:
        if self._dictionary_window is None:
            app_root = runtime_root()
            data_root = app_root / "data"
            manager = DictionaryManager(
                data_root / "terminology",
                source_dirs=[app_root / "resources", app_root / "resources" / "dictionaries", data_root],
            )
            self._dictionary_window = DictionaryWindow(manager)
        self._dictionary_window.open()

    @staticmethod
    def _load_language_rule() -> str:
        try:
            return resolve_language_rule(load_config())
        except Exception:
            logger.exception("failed to load input language rule")
            return "mixed"

    def _notify(self, message: str) -> None:
        if self._icon is None or not hasattr(self._icon, "notify"):
            return
        try:
            self._icon.notify(message, "VoiceDictation")
        except Exception:
            logger.exception("failed to show tray notification")

    def _select_language_rule(self, rule: str) -> bool:
        try:
            patch = language_settings_patch(rule)
            config = load_config()
            save_user_config_patch(patch, config)
        except Exception as exc:
            logger.exception("failed to save input language rule")
            self._notify(f"输入语言切换失败：{exc}")
            return False
        self._language_rule = rule
        if self._icon is not None:
            self._icon.update_menu()
        label = _LANGUAGE_RULE_BY_KEY[rule].label
        self._notify(f"已选择“{label}”，重启软件后生效")
        return True

    def _language_menu(self, pystray):
        return pystray.Menu(
            *(
                pystray.MenuItem(
                    option.label,
                    lambda _icon, _item, *, key=option.key: self._select_language_rule(key),
                    checked=lambda _item, key=option.key: self._language_rule == key,
                    radio=True,
                )
                for option in LANGUAGE_RULE_OPTIONS
            )
        )

    def _run(self) -> None:
        import pystray

        items = [
            pystray.MenuItem(lambda _item: f"当前热键：{self._chord_label}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("热键设置", lambda: self._on_open_hotkey_settings() if self._on_open_hotkey_settings else None, enabled=lambda _item: self._on_open_hotkey_settings is not None),
            pystray.MenuItem("输入语言规则（重启后生效）", self._language_menu(pystray)),
            pystray.MenuItem("词库管理", lambda: self._open_dictionary()),
            pystray.MenuItem("暂停听写" if not self._paused else "继续听写", lambda: self._on_toggle_pause()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("日志目录", lambda: self._on_open_logs() if self._on_open_logs else None, enabled=lambda _item: self._on_open_logs is not None),
            pystray.MenuItem("关于 RanLiAiJAY", lambda: self._on_open_about() if self._on_open_about else None, enabled=lambda _item: self._on_open_about is not None),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", lambda: self._request_quit()),
        ]
        self._icon = pystray.Icon("VoiceDictation", _load_icon(self.COLORS["idle"]), f"VoiceDictation（{self._chord_label}）", pystray.Menu(*items))
        self._icon.run()

    def set_chord_label(self, primary: str, secondary: str) -> None:
        from app.hotkey.keys import format_chord

        self._chord_label = format_chord(primary, secondary)
        if self._icon is not None:
            self._icon.update_menu()
        self.set_state(self._state)

    def set_state(self, state: str) -> None:
        self._state = state
        if self._icon is None:
            return
        try:
            self._icon.icon = _load_icon(self.COLORS.get(state, self.COLORS["idle"]))
            self._icon.title = f"VoiceDictation（{self._chord_label}）"
        except Exception:
            logger.exception("failed to update tray icon")

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        self.set_state("paused" if paused else "idle")

    def _request_quit(self) -> None:
        try:
            self._on_quit()
        finally:
            self.stop()

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                logger.exception("failed to stop tray")
            self._icon = None
