from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.ui import tray as tray_module
from app.ui.tray import (
    LANGUAGE_RULE_OPTIONS,
    TrayApp,
    language_settings_patch,
    resolve_language_rule,
    runtime_root,
)


def test_tray_exposes_dictionary_manager_action():
    tray = TrayApp(on_quit=lambda: None, on_toggle_pause=lambda: None)
    assert hasattr(tray, "_open_dictionary")
    assert "词库管理" in Path(TrayApp._run.__code__.co_filename).read_text(encoding="utf-8")


def test_tray_exposes_live_hotkey_status() -> None:
    source = Path(TrayApp._run.__code__.co_filename).read_text(encoding="utf-8")
    assert "当前热键" in source
    assert "update_menu" in source


def test_runtime_root_uses_executable_when_frozen(monkeypatch, tmp_path) -> None:
    executable = tmp_path / "VoiceDictation.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    assert runtime_root() == tmp_path


def test_tray_exposes_three_language_rules() -> None:
    assert tuple(option.label for option in LANGUAGE_RULE_OPTIONS) == (
        "中文为主",
        "英文为主",
        "中英文混合",
    )
    assert "输入语言规则" in Path(TrayApp._run.__code__.co_filename).read_text(encoding="utf-8")


def test_language_rule_maps_to_decoder_language() -> None:
    assert language_settings_patch("zh") == {
        "asr": {"language": "zh"},
        "postprocess": {"language_rule": "zh"},
    }
    assert language_settings_patch("en")["asr"]["language"] == "en"
    assert language_settings_patch("mixed")["asr"]["language"] == "auto"


def test_language_rule_resolves_legacy_configuration() -> None:
    assert resolve_language_rule({"asr": {"language": "zh"}}) == "zh"
    assert resolve_language_rule({"asr": {"language": "en"}}) == "en"
    assert resolve_language_rule({"asr": {"language": "auto"}}) == "mixed"


def test_real_pystray_menu_actions_select_each_language(monkeypatch) -> None:
    import pystray
    selected = []
    tray = TrayApp(on_quit=lambda: None, on_toggle_pause=lambda: None, language_rule="zh")
    monkeypatch.setattr(tray, "_select_language_rule", selected.append)
    menu = tray._language_menu(pystray)
    assert [item.text for item in menu.items] == ["中文为主", "英文为主", "中英文混合"]
    assert [item.checked for item in menu.items] == [True, False, False]
    for item in menu.items:
        item(None)
    assert selected == ["zh", "en", "mixed"]


def test_tray_language_selection_is_persisted(monkeypatch) -> None:
    saved = []
    config = {"paths": {"user_config": "config.yaml"}}
    monkeypatch.setattr(tray_module, "load_config", lambda: config)
    monkeypatch.setattr(
        tray_module,
        "save_user_config_patch",
        lambda patch, cfg: saved.append((patch, cfg)),
    )
    tray = TrayApp(
        on_quit=lambda: None,
        on_toggle_pause=lambda: None,
        language_rule="zh",
    )

    tray._select_language_rule("en")

    assert tray._language_rule == "en"
    assert saved == [(language_settings_patch("en"), config)]
