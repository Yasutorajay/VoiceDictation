from __future__ import annotations

from pathlib import Path

import pytest
from unittest.mock import patch

from app.hotkey.keys import KEY_LABELS, label_from_token, token_from_label
from app.ui.hotkey_settings import HotkeySelection, resolve_hotkey_selection
from app.ui.hotkey_settings import HotkeySettingsWindow


class FakeVariable:
    def __init__(self, value=None) -> None:
        self.value = value

    def get(self):
        return self.value

    def set(self, value) -> None:
        self.value = value


class FakeButton:
    def __init__(self) -> None:
        self.options = {}

    def configure(self, **kwargs) -> None:
        self.options.update(kwargs)


def test_manual_selection_resolves_to_tokens() -> None:
    selection = resolve_hotkey_selection("Right Ctrl", "F8")

    assert selection == HotkeySelection("right ctrl", "f8")


def test_invalid_manual_selection_is_rejected() -> None:
    with pytest.raises(ValueError):
        resolve_hotkey_selection("F8", "F8")


def test_empty_capture_does_not_replace_selection() -> None:
    selection = HotkeySelection("right alt", "mouse3")

    assert selection.with_capture("primary", "") == selection


def test_capture_updates_requested_slot() -> None:
    selection = HotkeySelection("right alt", "mouse3")

    assert selection.with_capture("primary", "left ctrl").primary == "left ctrl"
    assert selection.with_capture("secondary", "f9").secondary == "f9"


def test_capture_rejects_unknown_slot() -> None:
    with pytest.raises(ValueError):
        HotkeySelection("right alt", "mouse3").with_capture("other", "f8")


@pytest.mark.parametrize("token", sorted(set(KEY_LABELS) - {"escape"}))
def test_every_captured_key_label_round_trips(token: str) -> None:
    assert token_from_label(label_from_token(token)) == token


def test_window_preserves_explicit_open_contract() -> None:
    window = HotkeySettingsWindow(primary="right alt", secondary="mouse3", on_save=lambda *_: None)
    with patch("app.ui.hotkey_settings.threading.Thread") as thread:
        window.open()
        window.open()

    thread.assert_called_once()
    thread.return_value.start.assert_called_once()


def test_capture_immediately_updates_visible_key_fields() -> None:
    window = HotkeySettingsWindow(primary="right alt", secondary="mouse3", on_save=lambda *_: None)
    button = FakeButton()
    window._capture_button = button
    window._capture_slot = "primary"
    window._primary_var = FakeVariable("RightAlt")
    window._secondary_var = FakeVariable("鼠标中键 (Middle)")
    window._status_var = FakeVariable()

    window._apply_capture("primary", "down", button)

    assert window._primary_var.get() == "↓"
    assert window._secondary_var.get() == "鼠标中键 (Middle)"
    assert "待保存" in window._status_var.get()


def test_capture_preserves_other_key_selected_from_dropdown() -> None:
    window = HotkeySettingsWindow(primary="right alt", secondary="mouse3", on_save=lambda *_: None)
    button = FakeButton()
    window._capture_button = button
    window._capture_slot = "secondary"
    window._primary_var = FakeVariable("↓")
    window._secondary_var = FakeVariable("鼠标中键 (Middle)")
    window._status_var = FakeVariable()

    window._apply_capture("secondary", "f9", button)

    assert window._primary_var.get() == "↓"
    assert window._secondary_var.get() == "F9"


def test_save_reports_preview_now_and_performance_after_restart(monkeypatch, tmp_path) -> None:
    saved = []
    cfg = {"paths": {"data_dir": str(tmp_path), "logs_dir": str(tmp_path / "logs")}}
    window = HotkeySettingsWindow(
        primary="right alt",
        secondary="mouse3",
        on_save=lambda primary, secondary: saved.append((primary, secondary)),
        cfg=cfg,
    )
    window._primary_var = FakeVariable("↓")
    window._secondary_var = FakeVariable("Middle")
    window._retention_var = FakeVariable("7 天（推荐）")
    window._startup_var = FakeVariable(False)
    window._sound_var = FakeVariable(True)
    window._performance_var = FakeVariable("均衡模式（推荐）")
    window._preview_var = FakeVariable(False)
    window._save_capture_var = FakeVariable(False)
    window._status_var = FakeVariable()
    window._save_button = FakeButton()
    monkeypatch.setattr("app.ui.hotkey_settings.save_user_config_patch", lambda *_: None)
    monkeypatch.setattr("app.ui.hotkey_settings.update_runtime_config", lambda *_: None)
    monkeypatch.setattr("app.ui.hotkey_settings.set_startup_verified", lambda *_: None)
    monkeypatch.setattr("app.ui.hotkey_settings.cleanup_logs", lambda *_: 0)
    monkeypatch.setattr(
        "app.ui.hotkey_settings.messagebox.showerror",
        lambda *_args, **_kwargs: pytest.fail("save unexpectedly failed"),
    )

    window._save()

    assert saved == [("down", "mouse3")]
    assert "实时预览立即生效" in window._status_var.get()
    assert "运行模式重启后生效" in window._status_var.get()
    assert window._save_button.options["state"] == "normal"


def test_settings_window_no_longer_offers_recording_persistence() -> None:
    source = Path(HotkeySettingsWindow._run.__code__.co_filename).read_text(
        encoding="utf-8"
    )

    assert "保存最后一次录音用于排查问题" not in source


def test_startup_checkbox_applies_and_verifies_immediately(monkeypatch) -> None:
    applied = []
    window = HotkeySettingsWindow(
        primary="right alt",
        secondary="mouse3",
        on_save=lambda *_: None,
    )
    window._startup_var = FakeVariable(True)
    window._status_var = FakeVariable()
    monkeypatch.setattr(
        "app.ui.hotkey_settings.set_startup_verified",
        applied.append,
    )

    window._toggle_startup()

    assert applied == [True]
    assert "已开启并验证" in window._status_var.get()


def test_startup_verification_error_reloads_actual_state(monkeypatch) -> None:
    window = HotkeySettingsWindow(primary="right alt", secondary="mouse3", on_save=lambda *_: None)
    window._startup_var = FakeVariable(True)
    window._status_var = FakeVariable()
    def failed(_enabled):
        raise OSError("verification failed")
    monkeypatch.setattr("app.ui.hotkey_settings.set_startup_verified", failed)
    monkeypatch.setattr("app.ui.hotkey_settings.startup_enabled", lambda: True)
    monkeypatch.setattr("app.ui.hotkey_settings.messagebox.showerror", lambda *args, **kwargs: None)
    window._toggle_startup()
    assert window._startup_var.get() is True
    assert "已重新读取" in window._status_var.get()
