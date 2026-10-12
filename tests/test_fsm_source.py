from dataclasses import FrozenInstanceError
import pytest
from app.hotkey.fsm import HotkeyConfig, HotkeyFSM, HotkeyState


def make_fsm(*, secondary="mouse3", min_hold_ms=250):
    clock = [0]
    events = []
    fsm = HotkeyFSM(
        HotkeyConfig(secondary=secondary, min_hold_ms=min_hold_ms),
        on_start=lambda: events.append("start"),
        on_stop=lambda elapsed: events.append(("stop", elapsed)),
        on_cancel=lambda: events.append("cancel"),
        now_ms=lambda: clock[0],
    )
    return fsm, clock, events


def test_pulse_chord_starts_and_stops_after_primary_release():
    fsm, clock, events = make_fsm()
    assert fsm.on_key("mouse3", True) is False
    assert fsm.on_key("right alt", True) is False
    assert fsm.on_key("mouse3", True) is True
    assert fsm.is_recording
    clock[0] = 300
    assert fsm.on_key("mouse3", False) is True
    assert fsm.is_recording
    assert fsm.on_key("right alt", False) is False
    assert events == ["start", ("stop", 300)]
    assert fsm.state is HotkeyState.COOLDOWN


def test_short_press_cancels_and_cooldown_blocks_restart():
    fsm, clock, events = make_fsm()
    fsm.on_key("right alt", True)
    fsm.on_key("mouse3", True)
    clock[0] = 100
    fsm.on_key("right alt", False)
    assert events == ["start", "cancel"]
    assert fsm.on_key("mouse3", True) is True
    clock[0] = 251
    assert fsm.on_key("right alt", True) is False
    assert fsm.on_key("mouse3", True) is True
    assert events == ["start", "cancel", "start"]


def test_hold_secondary_release_stops_recording():
    fsm, clock, events = make_fsm(secondary="a")
    fsm.on_key("right alt", True)
    assert fsm.on_key("a", True) is True
    clock[0] = 260
    assert fsm.on_key("a", False) is True
    assert events == ["start", ("stop", 260)]


def test_busy_pause_and_escape():
    fsm, clock, events = make_fsm()
    fsm.set_busy(True)
    fsm.on_key("right alt", True)
    assert fsm.on_key("mouse3", True) is True
    assert events == []
    fsm.set_busy(False)
    assert fsm.on_key("mouse3", True) is True
    assert fsm.on_key("escape", True) is True
    assert events == ["start", "cancel"]
    clock[0] = 200
    fsm.on_key("right alt", True)
    fsm.on_key("mouse3", True)
    fsm.set_paused(True)
    assert not fsm.is_recording


def test_disabled_config_does_not_start():
    fsm, _, events = make_fsm()
    fsm.update_config(HotkeyConfig(enabled=False))
    fsm.on_key("right alt", True)
    fsm.on_key("mouse3", True)
    assert events == []

def test_hotkey_config_is_immutable():
    config = HotkeyConfig()
    with pytest.raises(FrozenInstanceError):
        config.primary = 'a'
