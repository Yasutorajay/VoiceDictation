import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ui.fallback_textbox import (
    FallbackTextBox,
    PIN_BUTTON_OFF_TEXT,
    PIN_BUTTON_ON_TEXT,
    SUPPORT_TEXT,
    WINDOW_GEOMETRY,
    WINDOW_MIN_SIZE,
)
import main


class _FakeRoot:
    def __init__(self):
        self.topmost = False
        self.calls = []

    def state(self):
        return "withdrawn"

    def deiconify(self):
        self.calls.append("deiconify")

    def lift(self):
        self.calls.append("lift")

    def attributes(self, name, value=None):
        self.calls.append((name, value))
        if name == "-topmost" and value is not None:
            self.topmost = value
        return self.topmost

    def after(self, *args):
        self.calls.append(tuple(args))

    def focus_set(self):
        pass


class _FakePinButton:
    def __init__(self):
        self.text = None
        self.style = None

    def configure(self, **kwargs):
        self.text = kwargs.get("text", self.text)
        self.style = kwargs.get("style", self.style)


def test_double_f10_window_toggle_logic(monkeypatch):
    box = FallbackTextBox()
    calls = []
    box.toggle = lambda: calls.append("toggle")
    box._on_f10(None)
    box._last_f10 -= 0.1
    box._on_f10(None)
    assert calls == ["toggle"]


def test_bridge_updates_only_failed_injection(monkeypatch):
    seen = []
    original = lambda text, cfg: {"ok": False, "error": "blocked"}
    def update(text, error):
        seen.append((text, error))
    result = original("abc", {})
    if not result["ok"]:
        update("abc", result["error"])
    assert seen == [("abc", "blocked")]


def test_history_keeps_latest_five_and_shortens_long_items():
    box = FallbackTextBox()
    for index in range(7):
        box._history.append(("x" * 250 + str(index), index % 2 == 0))
    assert len(box._history) == 5


def test_copy_action_uses_current_result_only():
    box = FallbackTextBox()
    class Root:
        def clipboard_clear(self): pass
        def clipboard_append(self, value): self.value = value
    root = Root(); box._root = root
    box._history.append(("旧结果", False)); box._history.append(("本次结果", True))
    box._copy()
    assert root.value == "本次结果"


def test_fallback_hotkey_bindings_include_ctrl_f10():
    box = FallbackTextBox()
    source = Path(FallbackTextBox.start_hotkey_listener.__code__.co_filename).read_text(encoding="utf-8")
    assert 'keyboard.add_hotkey("ctrl+f10"' in source


def test_copy_action_uses_current_result_only(monkeypatch):
    box = FallbackTextBox()
    class Root:
        def clipboard_clear(self): pass
        def clipboard_append(self, value): self.value = value
    root = Root(); box._root = root
    box._history.append(("旧结果", False)); box._history.append(("本次结果", True))
    box._copy()
    assert root.value == "本次结果"
    assert box._shorten("x" * 250).endswith("…")


def test_copy_button_is_named_for_current_result() -> None:
    source = Path(FallbackTextBox._run.__code__.co_filename).read_text(encoding="utf-8")

    assert 'text="复制本次结果"' in source


def test_bridge_replaces_pipeline_worker_cached_inject(monkeypatch):
    recorded = []

    class FakeBox:
        def start_hotkey_listener(self):
            pass

        def set_text(self, text, error=None):
            recorded.append((text, error))

    monkeypatch.setattr(main, "FallbackTextBox", FakeBox)
    monkeypatch.setattr(
        main.clipboard_inject,
        "inject_text",
        lambda text, cfg: {"ok": True, "method": "ctrl_v", "error": None},
    )

    main._install_fallback_bridge()
    result = main.pipeline_worker.inject_text("真实识别结果", {})

    assert result["ok"] is True
    assert recorded == [("真实识别结果", None)]


def test_window_uses_measured_size_and_branding():
    assert WINDOW_GEOMETRY == "620x435"
    assert WINDOW_MIN_SIZE == (620, 435)
    assert SUPPORT_TEXT == "燃力AiJay 提供技术支持"


def test_set_text_updates_without_forcing_window_visible():
    source = Path(FallbackTextBox.set_text.__code__.co_filename).read_text(encoding="utf-8")
    method = source.split("    def set_text", 1)[1].split("    @staticmethod", 1)[0]
    assert "deiconify" not in method
    assert "lift()" not in method


def test_overlay_show_api_keeps_application_keyword_signature() -> None:
    from app.ui.overlay import StatusOverlay

    overlay = StatusOverlay()
    overlay.show("录音中", mode="recording")
    overlay.show_partial("partial")
    overlay.set_levels([0.2, 0.4])


def test_fallback_bridge_preserves_injection_context(monkeypatch) -> None:
    calls: list[tuple[str, dict, dict]] = []

    class FakeTextBox:
        def start_hotkey_listener(self) -> None:
            return None

        def set_text(self, _text: str, _error: str | None) -> None:
            return None

    def inject(text: str, cfg: dict, **kwargs) -> dict:
        calls.append((text, cfg, kwargs))
        return {"ok": True}

    monkeypatch.setattr(main, "FallbackTextBox", FakeTextBox)
    monkeypatch.setattr(main.clipboard_inject, "inject_text", inject)
    main._install_fallback_bridge()
    cancelled = lambda: False
    gate = object()

    result = main.pipeline_worker.inject_text(
        "测试输出",
        {"inject": {}},
        target_window=123,
        cancelled=cancelled,
        input_gate=gate,
    )

    assert result == {"ok": True}
    assert calls == [
        (
            "测试输出",
            {"inject": {}},
            {"target_window": 123, "cancelled": cancelled, "input_gate": gate},
        )
    ]


def test_pin_toggle_switches_topmost_and_button_label():
    box = FallbackTextBox()
    root = _FakeRoot()
    box._root = root
    button = _FakePinButton()
    box._pin_button = button

    box._toggle_pin()
    assert box._pinned is True
    assert root.topmost is True
    assert button.text == PIN_BUTTON_ON_TEXT
    assert button.style == "FallbackPinOn.TButton"

    box._toggle_pin()
    assert box._pinned is False
    assert root.topmost is False
    assert button.text == PIN_BUTTON_OFF_TEXT
    assert button.style == "FallbackPin.TButton"


def test_pin_toggle_reverts_state_when_window_destroyed():
    box = FallbackTextBox()

    class DestroyedRoot:
        def attributes(self, name, value=None):
            raise tk.TclError()

    box._root = DestroyedRoot()
    box._toggle_pin()
    assert box._pinned is False


def test_show_keeps_topmost_when_pinned():
    box = FallbackTextBox()
    root = _FakeRoot()
    box._root = root
    box._pinned = True

    box._toggle_ui()
    assert ("-topmost", True) in root.calls
    assert (250, box._release_topmost) not in root.calls


def test_show_releases_temporary_topmost_when_not_pinned():
    box = FallbackTextBox()
    root = _FakeRoot()
    box._root = root
    box._pinned = False

    box._toggle_ui()
    assert ("-topmost", True) in root.calls
    assert (250, box._release_topmost) in root.calls


def test_release_topmost_keeps_window_pinned():
    box = FallbackTextBox()
    root = _FakeRoot()
    box._root = root
    box._pinned = True

    box._release_topmost()
    assert all(call[0] != "-topmost" for call in root.calls)


def test_pin_button_rendered_in_window_bottom_bar():
    source = Path(FallbackTextBox._run.__code__.co_filename).read_text(encoding="utf-8")
    assert "command=self._toggle_pin" in source
    assert PIN_BUTTON_OFF_TEXT in source
