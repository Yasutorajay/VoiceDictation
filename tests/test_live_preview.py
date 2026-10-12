import threading

import numpy as np

from app.worker.live_preview import LivePreview, _clean_partial


class FakeEngine:
    cfg = {"audio": {"sample_rate": 16000}}


def test_clean_partial_removes_model_tokens() -> None:
    assert _clean_partial("<|zh|><|NEUTRAL|>你好") == "你好"


def test_preview_reuses_pipeline_engine() -> None:
    engine = FakeEngine()

    preview = LivePreview(engine)

    assert preview._engine is engine


def test_stop_is_non_blocking() -> None:
    preview = LivePreview(FakeEngine())

    class Thread:
        def is_alive(self):
            return True

        def join(self, timeout):
            raise AssertionError("stop must not wait for decoding")

    preview._thread = Thread()
    preview._get_audio = lambda: np.zeros(1, dtype=np.float32)

    preview.stop()

    assert preview._thread is None


def test_preview_limits_audio_window() -> None:
    preview = LivePreview(FakeEngine(), sample_rate=10, min_audio_ms=100, max_audio_ms=500)
    seen = []
    preview._engine.transcribe = lambda audio: seen.append(audio.copy()) or "partial"
    preview._get_audio = lambda: np.arange(20, dtype=np.float32)
    preview._on_partial = lambda _text: None

    preview._tick()

    assert seen[0].tolist() == [15.0, 16.0, 17.0, 18.0, 19.0]


def test_preview_skips_transcribe_when_audio_unchanged() -> None:
    preview = LivePreview(FakeEngine(), sample_rate=10, min_audio_ms=100, max_audio_ms=500)
    seen = []
    preview._engine.transcribe = lambda audio: seen.append(audio.copy()) or "partial"
    preview._get_audio = lambda: np.arange(20, dtype=np.float32)
    preview._on_partial = lambda _text: None

    preview._tick()
    preview._tick()

    assert len(seen) == 1


def test_preview_retries_when_audio_grows() -> None:
    preview = LivePreview(FakeEngine(), sample_rate=10, min_audio_ms=100, max_audio_ms=500)
    seen = []
    preview._engine.transcribe = lambda audio: seen.append(audio.copy()) or "partial"
    buffers = [np.arange(20, dtype=np.float32), np.arange(24, dtype=np.float32)]
    preview._get_audio = lambda: buffers[min(len(seen), 1)]
    preview._on_partial = lambda _text: None

    preview._tick()
    preview._tick()

    assert len(seen) == 2


def test_preview_skips_tick_while_transcribe_running() -> None:
    preview = LivePreview(FakeEngine(), sample_rate=10, min_audio_ms=100, max_audio_ms=500)
    preview._get_audio = lambda: np.arange(20, dtype=np.float32)
    preview._on_partial = lambda _text: None
    preview._busy = True
    calls = []
    preview._engine.transcribe = lambda audio: calls.append(audio) or "partial"

    preview._tick()

    assert calls == []


def test_preview_defaults_use_low_latency_tuning() -> None:
    preview = LivePreview(FakeEngine())
    assert preview.interval_ms == 250
    assert preview.min_audio_ms == 250
    assert preview.max_audio_ms == 6000
