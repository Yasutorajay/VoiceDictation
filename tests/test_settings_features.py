from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from app import config as config_module
from app.config import cleanup_logs, load_config, normalize_retention_days
from app.hotkey.keys import format_chord, normalize_key, validate_hotkey_pair
from app.ui import hotkey_settings
from app.ui.hotkey_settings import (
    performance_settings_patch,
    startup_command,
    startup_value_matches,
)


def test_hotkey_requires_two_distinct_keys() -> None:
    assert validate_hotkey_pair("right alt", "mouse3") is None
    assert validate_hotkey_pair("right alt", "right alt")
    assert validate_hotkey_pair("mouse3", "right alt")
    assert format_chord("right alt", "mouse3") == "RightAlt + Middle"


def test_low_memory_mode_forces_live_preview_off() -> None:
    patch = performance_settings_patch(
        "低内存模式（首次使用加载）", True
    )

    assert patch["performance"]["mode"] == "low_memory"
    assert patch["live_preview"]["enabled"] is False
    assert patch["recording"] == {
        "save_last_capture": False,
        "save_last_result": False,
    }


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("极速模式（模型全部常驻）", "speed"),
        ("均衡模式（推荐）", "balanced"),
        ("低内存模式（首次使用加载）", "low_memory"),
    ],
)
def test_every_performance_selection_maps_to_a_runtime_mode(
    label: str, expected: str
) -> None:
    patch = performance_settings_patch(label, False)

    assert patch["performance"]["mode"] == expected


def test_loading_config_hard_disables_audio_and_text_persistence(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        "recording:\n  save_last_capture: true\n  save_last_result: true\n",
        encoding="utf-8",
    )

    loaded = load_config(config)

    assert loaded["recording"] == {
        "save_last_capture": False,
        "save_last_result": False,
    }


def test_loading_config_removes_legacy_audio_and_text_files(tmp_path: Path) -> None:
    logs = tmp_path / "data" / "logs"
    logs.mkdir(parents=True)
    (logs / "last_capture.wav").write_bytes(b"audio")
    (logs / "last_result.txt").write_text("private", encoding="utf-8")
    config = tmp_path / "config.yaml"
    config.write_text(
        f"paths:\n  data_dir: '{(tmp_path / 'data').as_posix()}'\n",
        encoding="utf-8",
    )

    load_config(config)

    assert not (logs / "last_capture.wav").exists()
    assert not (logs / "last_result.txt").exists()


def test_loading_config_does_not_follow_linked_logs_directory(tmp_path: Path) -> None:
    data = tmp_path / "data"
    outside = tmp_path / "outside"
    data.mkdir()
    outside.mkdir()
    private_file = outside / "last_result.txt"
    private_file.write_text("keep", encoding="utf-8")
    logs = data / "logs"
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(logs), str(outside)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            pytest.skip(f"Directory junctions are unavailable: {result.stderr}")
    else:
        logs.symlink_to(outside, target_is_directory=True)
    config = tmp_path / "config.yaml"
    config.write_text(
        f"paths:\n  data_dir: '{data.as_posix()}'\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unsafe logs directory"):
        load_config(config)

    assert private_file.read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1, 1), (3, 3), (7, 7), (30, 30), (None, None), ("never", None), (99, 7)],
)
def test_retention_normalization(value: object, expected: int | None) -> None:
    assert normalize_retention_days(value) == expected


def test_cleanup_logs_keeps_current_log(tmp_path: Path) -> None:
    old = tmp_path / "last_capture.wav"
    unrelated = tmp_path / "old_notes.txt"
    current = tmp_path / "app.log"
    fresh = tmp_path / "fresh.log"
    for path in (old, unrelated, current, fresh):
        path.write_text("x", encoding="utf-8")
    old_time = time.time() - 4 * 86400
    os.utime(old, (old_time, old_time))
    os.utime(unrelated, (old_time, old_time))
    os.utime(current, (old_time, old_time))
    assert cleanup_logs(tmp_path, 3) == 1
    assert not old.exists()
    assert unrelated.exists()
    assert current.exists()
    assert fresh.exists()


def test_cleanup_logs_uses_verified_handle_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    logs = tmp_path / "data" / "logs"
    logs.mkdir(parents=True)
    old = logs / "old.log"
    old.write_text("x", encoding="utf-8")
    old_time = time.time() - 4 * 86400
    os.utime(old, (old_time, old_time))
    calls: list[tuple[Path, Path]] = []
    real_delete = config_module.delete_file_by_verified_handle

    def record_delete(path: Path, expected: Path) -> bool:
        calls.append((path, expected))
        return real_delete(path, expected)

    monkeypatch.setattr(
        config_module,
        "delete_file_by_verified_handle",
        record_delete,
    )

    assert cleanup_logs(logs, 3, tmp_path / "data") == 1
    assert calls == [(old, logs.resolve() / old.name)]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Spacebar", "space"),
        ("Escape", "esc"),
        ("AltGr", "right alt"),
        ("LCTRL", "left ctrl"),
        ("Mouse Button 3", "mouse3"),
        ("XButton1", "mouse4"),
        ("Tilt Right", "wheel_right"),
        ("Left Cmd", "left windows"),
    ],
)
def test_platform_key_aliases_are_normalized(raw: str, expected: str) -> None:
    assert normalize_key(raw) == expected


def test_cleanup_rejects_untrusted_log_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        cleanup_logs(tmp_path / "elsewhere", 3, tmp_path)


def test_startup_command_quotes_executable(tmp_path: Path) -> None:
    executable = tmp_path / "语音 听写.exe"
    assert startup_command(executable) == f'"{executable.resolve()}"'


def test_startup_command_preserves_installed_link(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    installed = tmp_path / "Installed VoiceDictation.exe"
    hidden_target = tmp_path / "hidden" / "VoiceDictation.exe"
    original_resolve = Path.resolve

    def resolve(path: Path, *args: object, **kwargs: object) -> Path:
        return hidden_target if path == installed else original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)

    assert startup_command(installed) == f'"{installed.absolute()}"'

def test_source_startup_command_includes_script(tmp_path: Path) -> None:
    executable = tmp_path / "python.exe"
    script = tmp_path / "main.py"
    assert startup_command(executable, script) == f'"{executable.resolve()}" "{script.resolve()}"'


def test_startup_value_matches_current_executable(tmp_path: Path) -> None:
    executable = tmp_path / "Voice Dictation.exe"
    command = startup_command(executable)

    assert startup_value_matches(command, command)


def test_startup_value_rejects_stale_executable(tmp_path: Path) -> None:
    current = startup_command(tmp_path / "current" / "VoiceDictation.exe")
    stale = startup_command(tmp_path / "old" / "VoiceDictation.exe")

    assert not startup_value_matches(stale, current)


def test_startup_value_ignores_surrounding_whitespace(tmp_path: Path) -> None:
    command = startup_command(tmp_path / "VoiceDictation.exe")

    assert startup_value_matches(f"  {command}  ", command)


def test_startup_enabled_rejects_stale_registry_value(monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[object] = []
    key = object()
    monkeypatch.setattr(hotkey_settings, "OpenKey", lambda *_args: key)
    monkeypatch.setattr(
        hotkey_settings,
        "QueryValueEx",
        lambda _key, _name: ('"C:\\Old\\VoiceDictation.exe"', hotkey_settings.REG_SZ),
    )
    monkeypatch.setattr(hotkey_settings, "CloseKey", closed.append)
    monkeypatch.setattr(
        hotkey_settings,
        "current_startup_command",
        lambda: '"C:\\Current\\VoiceDictation.exe"',
    )

    assert not hotkey_settings.startup_enabled()
    assert closed == [key]


def test_startup_enabled_accepts_current_registry_value(monkeypatch: pytest.MonkeyPatch) -> None:
    key = object()
    command = '"C:\\Current\\VoiceDictation.exe"'
    monkeypatch.setattr(hotkey_settings, "OpenKey", lambda *_args: key)
    monkeypatch.setattr(
        hotkey_settings,
        "QueryValueEx",
        lambda _key, _name: (command, hotkey_settings.REG_SZ),
    )
    monkeypatch.setattr(hotkey_settings, "CloseKey", lambda _key: None)
    monkeypatch.setattr(hotkey_settings, "current_startup_command", lambda: command)

    assert hotkey_settings.startup_enabled()


def test_startup_enabled_rejects_wrong_registry_type(monkeypatch: pytest.MonkeyPatch) -> None:
    key = object()
    command = '"C:\\Current\\VoiceDictation.exe"'
    monkeypatch.setattr(hotkey_settings, "OpenKey", lambda *_args: key)
    monkeypatch.setattr(
        hotkey_settings,
        "QueryValueEx",
        lambda _key, _name: (command, 2),
    )
    monkeypatch.setattr(hotkey_settings, "CloseKey", lambda _key: None)
    monkeypatch.setattr(hotkey_settings, "current_startup_command", lambda: command)

    assert not hotkey_settings.startup_enabled()


def test_set_startup_writes_current_command(monkeypatch: pytest.MonkeyPatch) -> None:
    written: list[tuple[object, str, int, int, str]] = []
    key = object()
    monkeypatch.setattr(hotkey_settings, "CreateKey", lambda *_args: key)
    monkeypatch.setattr(hotkey_settings, "SetValueEx", lambda *args: written.append(args))
    monkeypatch.setattr(hotkey_settings, "CloseKey", lambda _key: None)
    monkeypatch.setattr(
        hotkey_settings,
        "current_startup_command",
        lambda: '"C:\\Current\\VoiceDictation.exe"',
    )

    hotkey_settings.set_startup(True)

    assert written == [
        (
            key,
            hotkey_settings.RUN_VALUE,
            0,
            hotkey_settings.REG_SZ,
            '"C:\\Current\\VoiceDictation.exe"',
        )
    ]


def test_set_startup_disable_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    key = object()
    monkeypatch.setattr(hotkey_settings, "CreateKey", lambda *_args: key)
    monkeypatch.setattr(
        hotkey_settings,
        "DeleteValue",
        lambda *_args: (_ for _ in ()).throw(FileNotFoundError),
    )
    monkeypatch.setattr(hotkey_settings, "CloseKey", lambda _key: None)

    hotkey_settings.set_startup(False)


def test_set_startup_disable_deletes_value(monkeypatch: pytest.MonkeyPatch) -> None:
    deleted: list[tuple[object, str]] = []
    key = object()
    monkeypatch.setattr(hotkey_settings, "CreateKey", lambda *_args: key)
    monkeypatch.setattr(hotkey_settings, "DeleteValue", lambda *args: deleted.append(args))
    monkeypatch.setattr(hotkey_settings, "CloseKey", lambda _key: None)

    hotkey_settings.set_startup(False)

    assert deleted == [(key, hotkey_settings.RUN_VALUE)]


def test_startup_setting_is_verified_after_write(monkeypatch: pytest.MonkeyPatch) -> None:
    written: list[bool] = []
    monkeypatch.setattr(hotkey_settings, "set_startup", written.append)
    monkeypatch.setattr(hotkey_settings, "startup_enabled", lambda: True)

    hotkey_settings.set_startup_verified(True)

    assert written == [True]


def test_startup_setting_reports_registry_write_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hotkey_settings, "set_startup", lambda _enabled: None)
    monkeypatch.setattr(hotkey_settings, "startup_enabled", lambda: False)

    with pytest.raises(OSError, match="注册表"):
        hotkey_settings.set_startup_verified(True)


def test_explicit_user_config_wins(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("hotkey:\n  primary: f8\n  secondary: f9\n", encoding="utf-8")
    loaded = load_config(config)
    assert loaded["hotkey"]["primary"] == "f8"
    assert loaded["hotkey"]["secondary"] == "f9"


def test_absolute_log_subdir_cannot_escape_data_directory(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    config = tmp_path / "config.yaml"
    config.write_text(
        "paths:\n"
        f"  data_dir: '{(tmp_path / 'data').as_posix()}'\n"
        f"  log_subdir: '{outside.as_posix()}'\n",
        encoding="utf-8",
    )

    loaded = load_config(config)

    assert Path(loaded["paths"]["logs_dir"]).resolve() == (
        tmp_path / "data" / "logs"
    ).resolve()


def test_root_relative_models_subdir_cannot_escape_data_directory(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        "paths:\n"
        f"  data_dir: '{(tmp_path / 'data').as_posix()}'\n"
        "  models_subdir: '\\outside'\n",
        encoding="utf-8",
    )

    loaded = load_config(config)

    assert Path(loaded["paths"]["models_dir"]).resolve() == (
        tmp_path / "data" / "models"
    ).resolve()


def test_invalid_hotkey_falls_back_without_crashing(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        "hotkey:\n  primary: mouse3\n  secondary: f8\n",
        encoding="utf-8",
    )

    loaded = load_config(config)

    assert loaded["hotkey"]["primary"] == "right alt"
    assert loaded["hotkey"]["secondary"] == "mouse3"
