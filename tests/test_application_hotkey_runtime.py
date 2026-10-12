from pathlib import Path

from app.application import Application
from app import application
from app.config import load_config


class RuntimeTarget:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def update_config(self, config) -> None:
        self.calls.append(("update_config", config.primary, config.secondary))

    def set_bindings(self, primary: str, secondary: str) -> None:
        self.calls.append(("set_bindings", primary, secondary))

    def set_chord_label(self, primary: str, secondary: str) -> None:
        self.calls.append(("set_chord_label", primary, secondary))

    def set_state(self, state: str) -> None:
        self.calls.append(("set_state", state))


def test_apply_hotkey_updates_runtime_listener_and_tray(tmp_path: Path) -> None:
    user = tmp_path / "config.yaml"
    user.write_text("paths:\n  data_dir: data\n", encoding="utf-8")
    app = Application(load_config(user))
    fsm = RuntimeTarget()
    listener = RuntimeTarget()
    tray = RuntimeTarget()
    app._fsm = fsm
    app._listener = listener
    app._tray = tray

    app.apply_hotkey("down", "mouse3")

    assert app.cfg["hotkey"]["primary"] == "down"
    assert app.cfg["hotkey"]["secondary"] == "mouse3"
    assert ("update_config", "down", "mouse3") in fsm.calls
    assert ("set_bindings", "down", "mouse3") in listener.calls
    assert ("set_chord_label", "down", "mouse3") in tray.calls
    assert ("set_state", "idle") in tray.calls


def test_settings_window_receives_capture_and_runtime_callbacks(
    monkeypatch,
    tmp_path: Path,
) -> None:
    user = tmp_path / "config.yaml"
    user.write_text("paths:\n  data_dir: data\n", encoding="utf-8")
    app = Application(load_config(user))
    received: dict[str, object] = {}

    class FakeWindow:
        def __init__(self, **kwargs) -> None:
            received.update(kwargs)

        def open(self) -> None:
            received["opened"] = True

    monkeypatch.setattr(application, "HotkeySettingsWindow", FakeWindow)
    monkeypatch.setattr(app, "toggle_pause", lambda: None)

    applied: list[tuple[str, str]] = []
    app.apply_hotkey = lambda primary, secondary: applied.append((primary, secondary))

    app.open_hotkey_settings()

    on_save = received["on_save"]
    assert callable(on_save)
    on_save("down", "mouse3")
    assert applied == [("down", "mouse3")]
    assert callable(received["on_capture"])
    assert received["cfg"] is app.cfg
    assert received["opened"] is True
