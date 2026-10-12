from __future__ import annotations

import logging
import re
import threading
from typing import Callable

import numpy as np

from app.asr.engine import AsrEngine

logger = logging.getLogger(__name__)


def _clean_partial(text: str) -> str:
    return re.sub(r"<\|[^|]+\|>", "", text).strip()


class LivePreview:
    def __init__(
        self,
        engine: AsrEngine,
        *,
        sample_rate: int = 16000,
        interval_ms: int = 250,
        min_audio_ms: int = 250,
        max_audio_ms: int = 6000,
        on_partial: Callable[[str], None] | None = None,
    ) -> None:
        self._engine = engine
        self.sample_rate = sample_rate
        self.interval_ms = interval_ms
        self.min_audio_ms = min_audio_ms
        self.max_audio_ms = max_audio_ms
        self._on_partial = on_partial or (lambda _text: None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._get_audio: Callable[[], np.ndarray] | None = None
        self._last_text = ""
        self._lock = threading.Lock()
        self._busy = False
        self._audio_key: tuple[int, int] | None = None
        self._generation = 0
        self._thread_stop: threading.Event | None = None


    def start(self, get_audio: Callable[[], np.ndarray]) -> None:
        self.stop()
        self._get_audio = get_audio
        self._stop = threading.Event()
        self._thread_stop = self._stop
        self._generation += 1
        generation = self._generation
        self._audio_key = None
        with self._lock:
            self._last_text = ""
        self._thread = threading.Thread(
            target=self._loop,
            args=(self._stop, generation),
            name="live-preview",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        stop = self._thread_stop
        if stop is not None:
            stop.set()
        self._generation += 1
        self._thread = None
        self._thread_stop = None
        self._get_audio = None

    def _loop(self, stop: threading.Event, generation: int) -> None:
        try:
            if stop.wait(self.min_audio_ms / 1000.0):
                return
            while not stop.is_set():
                self._tick(generation)
                if stop.wait(self.interval_ms / 1000.0):
                    return
        except Exception:
            logger.exception("live preview failed")

    @staticmethod
    def _audio_fingerprint(audio: np.ndarray) -> tuple[int, int]:
        tail = audio[-32:] if audio.size > 32 else audio
        return (audio.size, hash(tail.tobytes()))

    def _tick(self, generation: int | None = None) -> None:
        if generation is not None and generation != self._generation:
            return
        # 上一次识别尚未完成时跳过本轮，避免预览请求在锁上排队堆积。
        if self._busy:
            return
        get_audio = self._get_audio
        if get_audio is None:
            return
        audio = get_audio()
        min_samples = int(self.sample_rate * self.min_audio_ms / 1000)
        if audio is None or audio.size < min_samples:
            return
        key = self._audio_fingerprint(audio)
        if key == self._audio_key:
            return
        self._audio_key = key
        max_samples = int(self.sample_rate * self.max_audio_ms / 1000)
        audio = audio[-max_samples:]
        rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2) + 1e-12))
        if rms < 0.004:
            return
        self._busy = True
        try:
            text = _clean_partial(self._engine.transcribe(audio))
        finally:
            self._busy = False
        if generation is not None and generation != self._generation:
            return
        if not text:
            return
        with self._lock:
            if text == self._last_text:
                return
            self._last_text = text
        self._on_partial(text)
