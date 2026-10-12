from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable

from app.hotkey.keys import is_pulse_token, normalize_key


class HotkeyState(Enum):
    IDLE = auto()
    PRIMARY_HELD = auto()
    RECORDING = auto()
    COOLDOWN = auto()


@dataclass
class HotkeyConfig:
    primary: str = "right alt"
    secondary: str = "mouse3"
    min_hold_ms: int = 250
    cooldown_ms: int = 150
    enabled: bool = True


class HotkeyFSM:
    def __init__(
        self,
        config: HotkeyConfig,
        *,
        on_start: Callable[[], None] | None = None,
        on_stop: Callable[[int], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        now_ms: Callable[[], int] | None = None,
    ) -> None:
        self.config = config
        self._on_start = on_start or (lambda: None)
        self._on_stop = on_stop or (lambda _ms: None)
        self._on_cancel = on_cancel or (lambda: None)
        self._now_ms = now_ms or self._default_now_ms
        self.state = HotkeyState.IDLE
        self._primary_down = False
        self._secondary_down = False
        self._record_started_ms = 0
        self._cooldown_until_ms = 0
        self._busy = False
        self._paused = False

    @staticmethod
    def _default_now_ms() -> int:
        return int(time.monotonic() * 1000)

    @property
    def is_recording(self) -> bool:
        return self.state == HotkeyState.RECORDING

    def update_config(self, config: HotkeyConfig) -> None:
        if self.is_recording:
            self._abort_recording(cancel=True)
        self.config = config
        self.state = HotkeyState.IDLE
        self._primary_down = False
        self._secondary_down = False

    def set_busy(self, busy: bool) -> None:
        self._busy = busy

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        if paused and self.is_recording:
            self._abort_recording(cancel=True)

    def _secondary_is_pulse(self) -> bool:
        return is_pulse_token(self.config.secondary)

    def on_key(self, key: str, is_down: bool) -> bool:
        if not self.config.enabled or self._paused:
            return False
        key = normalize_key(key)
        primary = normalize_key(self.config.primary)
        secondary = normalize_key(self.config.secondary)
        now = self._now_ms()
        if self.state == HotkeyState.COOLDOWN:
            if now >= self._cooldown_until_ms:
                self.state = HotkeyState.IDLE
            elif key == primary:
                self._primary_down = is_down
                return False
            elif key == secondary:
                return is_down or self._secondary_is_pulse()
        if key in ("esc", "escape") and is_down:
            if self.is_recording:
                self._abort_recording(cancel=True)
                return True
            return False
        if key == primary:
            return self._handle_primary(is_down, now)
        if key == secondary:
            return self._handle_secondary(is_down, now)
        return False

    def _handle_primary(self, is_down: bool, now: int) -> bool:
        self._primary_down = is_down
        if is_down:
            if self.state == HotkeyState.IDLE:
                self.state = HotkeyState.PRIMARY_HELD
            return False
        if self.is_recording:
            self._finish_recording(now)
        elif self.state == HotkeyState.PRIMARY_HELD:
            self.state = HotkeyState.IDLE
        return False

    def _handle_secondary(self, is_down: bool, now: int) -> bool:
        pulse = self._secondary_is_pulse()
        if is_down:
            if self.is_recording and pulse:
                self._finish_recording(now)
                return True
            if self.state == HotkeyState.PRIMARY_HELD and self._primary_down:
                if self._busy:
                    return True
                self._secondary_down = True
                self.state = HotkeyState.RECORDING
                self._record_started_ms = now
                self._on_start()
                return True
            return False
        was_down = self._secondary_down
        self._secondary_down = False
        if pulse:
            return was_down
        if self.is_recording and was_down:
            self._finish_recording(now)
            return True
        return False

    def _finish_recording(self, now: int) -> None:
        held = max(0, now - self._record_started_ms)
        self.state = HotkeyState.COOLDOWN
        self._cooldown_until_ms = now + self.config.cooldown_ms
        self._secondary_down = False
        if held < self.config.min_hold_ms:
            self._on_cancel()
        else:
            self._on_stop(held)

    def _abort_recording(self, *, cancel: bool) -> None:
        self.state = HotkeyState.COOLDOWN
        self._cooldown_until_ms = self._now_ms() + self.config.cooldown_ms
        self._secondary_down = False
        if cancel:
            self._on_cancel()