from __future__ import annotations

import ctypes
import threading

from app.inject import clipboard_inject


def test_windows_input_structure_matches_64_bit_abi() -> None:
    expected_size = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
    assert ctypes.sizeof(clipboard_inject.INPUT) == expected_size


def test_send_failure_includes_windows_error(monkeypatch) -> None:
    monkeypatch.setattr(clipboard_inject.pyperclip, "copy", lambda _text: None)
    monkeypatch.setattr(clipboard_inject.pyperclip, "paste", lambda: "")
    monkeypatch.setattr(clipboard_inject, "_release_modifiers", lambda: None)
    monkeypatch.setattr(clipboard_inject, "_send_paste", lambda _shortcut: (0, 87))
    monkeypatch.setattr(clipboard_inject, "_type_unicode", lambda _text: (0, 87))
    monkeypatch.setattr(clipboard_inject, "_foreground_window", lambda: 100)
    monkeypatch.setattr(clipboard_inject.time, "sleep", lambda _delay: None)

    result = clipboard_inject.inject_text("测试", {"inject": {}})

    assert result["ok"] is False
    assert "winerror=87" in result["error"]


def test_inject_uses_real_paste_with_configured_delays(monkeypatch) -> None:
    calls: list[object] = []
    clipboard_values = iter(("原剪贴板", "SeeDANCE 2.0"))
    monkeypatch.setattr(clipboard_inject.pyperclip, "copy", lambda text: calls.append(("copy", text)))
    monkeypatch.setattr(clipboard_inject.pyperclip, "paste", lambda: next(clipboard_values))
    monkeypatch.setattr(clipboard_inject, "_release_modifiers", lambda: calls.append("release"))
    monkeypatch.setattr(clipboard_inject, "_send_paste", lambda shortcut: calls.append(("paste", shortcut)) or (4, 0))
    monkeypatch.setattr(clipboard_inject, "_foreground_window", lambda: 100)
    monkeypatch.setattr(clipboard_inject.time, "sleep", lambda delay: calls.append(("sleep", delay)))

    result = clipboard_inject.inject_text(
        "SeeDANCE 2.0",
        {"inject": {"pre_paste_delay_ms": 90, "post_paste_delay_ms": 180}},
    )

    assert result == {"ok": True, "method": "ctrl_v", "error": None}
    assert calls == [
        ("copy", "SeeDANCE 2.0"),
        "release",
        ("sleep", 0.09),
        ("paste", "ctrl_v"),
        ("sleep", 0.18),
        ("copy", "原剪贴板"),
    ]


def test_shift_insert_can_be_selected_for_incompatible_controls(monkeypatch) -> None:
    monkeypatch.setattr(clipboard_inject.pyperclip, "copy", lambda _text: None)
    monkeypatch.setattr(clipboard_inject.pyperclip, "paste", lambda: "")
    monkeypatch.setattr(clipboard_inject, "_release_modifiers", lambda: None)
    monkeypatch.setattr(clipboard_inject.time, "sleep", lambda _delay: None)
    shortcuts: list[str] = []
    monkeypatch.setattr(clipboard_inject, "_send_paste", lambda shortcut: shortcuts.append(shortcut) or (4, 0))
    monkeypatch.setattr(clipboard_inject, "_foreground_window", lambda: 100)

    result = clipboard_inject.inject_text(
        "受控输入框",
        {"inject": {"paste_shortcut": "shift_insert"}},
    )

    assert result["ok"] is True
    assert result["method"] == "shift_insert"
    assert shortcuts == ["shift_insert"]


def test_failed_injection_leaves_text_on_clipboard(monkeypatch) -> None:
    copied: list[str] = []
    monkeypatch.setattr(clipboard_inject.pyperclip, "copy", copied.append)
    monkeypatch.setattr(clipboard_inject.pyperclip, "paste", lambda: "旧内容")
    monkeypatch.setattr(clipboard_inject, "_release_modifiers", lambda: None)
    monkeypatch.setattr(clipboard_inject, "_send_paste", lambda _shortcut: (0, 5))
    monkeypatch.setattr(clipboard_inject, "_type_unicode", lambda _text: (0, 5))
    monkeypatch.setattr(clipboard_inject, "_foreground_window", lambda: 100)
    monkeypatch.setattr(clipboard_inject.time, "sleep", lambda _delay: None)

    result = clipboard_inject.inject_text("不能丢失", {"inject": {}})

    assert result["ok"] is False
    assert result["method"] == "clipboard_only"
    assert copied[-1] == "不能丢失"


def test_clipboard_restore_failure_does_not_double_type(monkeypatch) -> None:
    copied: list[str] = []
    monkeypatch.setattr(clipboard_inject.pyperclip, "paste", lambda: "旧内容")
    monkeypatch.setattr(clipboard_inject, "_release_modifiers", lambda: None)
    monkeypatch.setattr(clipboard_inject, "_send_paste", lambda _shortcut: (4, 0))
    monkeypatch.setattr(clipboard_inject, "_foreground_window", lambda: 100)
    monkeypatch.setattr(clipboard_inject.time, "sleep", lambda _delay: None)

    def copy(text: str) -> None:
        copied.append(text)
        if text == "旧内容":
            raise RuntimeError("clipboard locked")

    monkeypatch.setattr(clipboard_inject.pyperclip, "copy", copy)
    typed: list[object] = []
    monkeypatch.setattr(clipboard_inject, "_type_unicode", lambda text: typed.append(text) or (0, 5))

    result = clipboard_inject.inject_text("已粘贴成功", {"inject": {}})

    assert result == {"ok": True, "method": "ctrl_v", "error": None}
    assert typed == []


def test_focus_change_aborts_without_typing(monkeypatch) -> None:
    windows = iter((100, 200))
    monkeypatch.setattr(clipboard_inject, "_foreground_window", lambda: next(windows))
    clipboard_values = iter(("旧内容", "敏感内容"))
    monkeypatch.setattr(clipboard_inject.pyperclip, "paste", lambda: next(clipboard_values))
    copied: list[str] = []
    monkeypatch.setattr(clipboard_inject.pyperclip, "copy", copied.append)
    monkeypatch.setattr(clipboard_inject, "_release_modifiers", lambda: None)
    monkeypatch.setattr(clipboard_inject.time, "sleep", lambda _delay: None)
    monkeypatch.setattr(clipboard_inject, "_send_paste", lambda _shortcut: (4, 0))
    monkeypatch.setattr(clipboard_inject, "_type_unicode", lambda _text: (0, 5))

    result = clipboard_inject.inject_text("敏感内容", {"inject": {}})

    assert result["ok"] is False
    assert "focus_changed" in result["error"]
    assert copied == ["敏感内容", "旧内容"]


def test_explicit_target_window_is_checked_before_clipboard_write(monkeypatch) -> None:
    copied: list[str] = []
    monkeypatch.setattr(clipboard_inject.pyperclip, "copy", copied.append)
    monkeypatch.setattr(clipboard_inject.pyperclip, "paste", lambda: "旧内容")
    monkeypatch.setattr(clipboard_inject, "_foreground_window", lambda: 200)

    result = clipboard_inject.inject_text("不能输错窗口", {"inject": {}}, target_window=100)

    assert result["ok"] is False
    assert result["error"] == "focus_changed"
    assert copied == []


def test_clipboard_restore_does_not_overwrite_new_user_content(monkeypatch) -> None:
    clipboard_values = iter(("旧内容", "用户刚复制的新内容"))
    copied: list[str] = []
    monkeypatch.setattr(clipboard_inject.pyperclip, "paste", lambda: next(clipboard_values))
    monkeypatch.setattr(clipboard_inject.pyperclip, "copy", copied.append)
    monkeypatch.setattr(clipboard_inject, "_release_modifiers", lambda: None)
    monkeypatch.setattr(clipboard_inject, "_send_paste", lambda _shortcut: (4, 0))
    monkeypatch.setattr(clipboard_inject, "_foreground_window", lambda: 100)
    monkeypatch.setattr(clipboard_inject.time, "sleep", lambda _delay: None)

    result = clipboard_inject.inject_text("听写结果", {"inject": {}})

    assert result["ok"] is True
    assert copied == ["听写结果"]


def test_unicode_fallback_rechecks_focus(monkeypatch) -> None:
    windows = iter((100, 100, 200))
    clipboard_values = iter(("旧内容", "听写结果"))
    copied: list[str] = []
    typed: list[str] = []
    monkeypatch.setattr(clipboard_inject, "_foreground_window", lambda: next(windows))
    monkeypatch.setattr(clipboard_inject.pyperclip, "paste", lambda: next(clipboard_values))
    monkeypatch.setattr(clipboard_inject.pyperclip, "copy", copied.append)
    monkeypatch.setattr(clipboard_inject, "_release_modifiers", lambda: None)
    monkeypatch.setattr(clipboard_inject, "_send_paste", lambda _shortcut: (0, 5))
    monkeypatch.setattr(clipboard_inject, "_type_unicode", lambda text: typed.append(text) or (len(text) * 2, 0))
    monkeypatch.setattr(clipboard_inject.time, "sleep", lambda _delay: None)

    result = clipboard_inject.inject_text("听写结果", {"inject": {}}, target_window=100)

    assert result["ok"] is False
    assert "focus_changed" in result["error"]
    assert typed == []
    assert copied == ["听写结果", "旧内容"]


def test_paste_send_is_guarded_by_shared_input_gate(monkeypatch) -> None:
    gate = threading.Lock()
    guarded: list[bool] = []
    clipboard_values = iter(("旧内容", "听写结果"))
    monkeypatch.setattr(clipboard_inject.pyperclip, "paste", lambda: next(clipboard_values))
    monkeypatch.setattr(clipboard_inject.pyperclip, "copy", lambda _text: None)
    monkeypatch.setattr(clipboard_inject, "_release_modifiers", lambda: None)
    monkeypatch.setattr(clipboard_inject, "_foreground_window", lambda: 100)
    monkeypatch.setattr(clipboard_inject.time, "sleep", lambda _delay: None)

    def send(_shortcut):
        acquired = gate.acquire(blocking=False)
        guarded.append(not acquired)
        if acquired:
            gate.release()
        return 4, 0

    monkeypatch.setattr(clipboard_inject, "_send_paste", send)

    result = clipboard_inject.inject_text(
        "听写结果",
        {"inject": {}},
        target_window=100,
        input_gate=gate,
    )

    assert result["ok"] is True
    assert guarded == [True]
