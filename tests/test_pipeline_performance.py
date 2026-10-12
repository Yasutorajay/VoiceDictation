import logging
from pathlib import Path

import numpy as np

from app.worker import pipeline_worker
from app.worker.pipeline_worker import PipelineWorker
from app.asr.process_engine import ProcessAsrEngine


class FakeEngine:
    def __init__(self) -> None:
        self.loaded = False
        self.load_calls: list[bool] = []
        self.closed = False

    @property
    def is_loaded(self) -> bool:
        return self.loaded

    def load(self, *, load_punctuation: bool = True) -> None:
        self.load_calls.append(load_punctuation)
        self.loaded = True

    def transcribe(self, _audio: np.ndarray) -> str:
        return "测试"

    def punctuate(self, text: str) -> str:
        return text

    def release_if_idle(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def config(tmp_path: Path, mode: str, *, save_last_capture: bool = True) -> dict:
    return {
        "audio": {"sample_rate": 16000, "silence_rms": 0.0, "pad_ms": 0},
        "asr": {},
        "performance": {"mode": mode, "idle_unload_minutes": 10},
        "live_preview": {"enabled": False},
        "recording": {"save_last_capture": save_last_capture},
        "punctuation": {"enabled": False},
        "postprocess": {"remove_fillers": False, "polish_punctuation": False},
        "terminology": {"enabled": False},
        "inject": {"method": "auto"},
        "paths": {"logs_dir": str(tmp_path)},
    }


def test_balanced_start_eagerly_loads_only_main_model(tmp_path: Path) -> None:
    engine = FakeEngine()
    worker = PipelineWorker(config(tmp_path, "balanced"), engine=engine)

    worker.start()
    worker.shutdown()

    assert engine.load_calls == [False]
    assert engine.closed is True


def test_low_memory_start_does_not_load_model(tmp_path: Path) -> None:
    engine = FakeEngine()
    worker = PipelineWorker(config(tmp_path, "low_memory"), engine=engine)

    worker.start()
    worker.shutdown()

    assert engine.load_calls == []


def test_first_low_memory_transcription_loads_without_preview_text(
    tmp_path: Path, monkeypatch
) -> None:
    engine = FakeEngine()
    partials: list[str] = []
    worker = PipelineWorker(
        config(tmp_path, "low_memory"), engine=engine, on_partial=partials.append
    )
    monkeypatch.setattr(pipeline_worker, "trim_silence", lambda audio, *_args, **_kwargs: audio)
    monkeypatch.setattr(pipeline_worker, "postprocess_text", lambda text, *_args, **_kwargs: text)
    monkeypatch.setattr(pipeline_worker, "inject_text", lambda *_args, **_kwargs: {"ok": True})

    worker._handle_transcribe(np.ones(16, dtype=np.float32), 1)

    assert engine.load_calls == [False]
    assert partials == []


def test_last_capture_can_be_disabled(tmp_path: Path, monkeypatch) -> None:
    engine = FakeEngine()
    engine.loaded = True
    worker = PipelineWorker(
        config(tmp_path, "balanced", save_last_capture=False), engine=engine
    )
    saved: list[object] = []
    monkeypatch.setattr(pipeline_worker, "trim_silence", lambda audio, *_args, **_kwargs: audio)
    monkeypatch.setattr(
        pipeline_worker,
        "save_wav",
        lambda *args: saved.append(args),
        raising=False,
    )
    monkeypatch.setattr(pipeline_worker, "postprocess_text", lambda text, *_args, **_kwargs: text)
    monkeypatch.setattr(pipeline_worker, "inject_text", lambda *_args, **_kwargs: {"ok": True})

    worker._handle_transcribe(np.ones(16, dtype=np.float32), 1)

    assert saved == []


def test_audio_and_text_are_never_persisted_even_if_config_is_tampered(
    tmp_path: Path, monkeypatch
) -> None:
    engine = FakeEngine()
    engine.loaded = True
    cfg = config(tmp_path, "balanced", save_last_capture=True)
    cfg["recording"]["save_last_result"] = True
    worker = PipelineWorker(cfg, engine=engine)
    saved_audio: list[object] = []
    monkeypatch.setattr(pipeline_worker, "trim_silence", lambda audio, *_args, **_kwargs: audio)
    monkeypatch.setattr(
        pipeline_worker,
        "save_wav",
        lambda *args: saved_audio.append(args),
        raising=False,
    )
    monkeypatch.setattr(pipeline_worker, "postprocess_text", lambda text, *_args, **_kwargs: text)
    monkeypatch.setattr(pipeline_worker, "inject_text", lambda *_args, **_kwargs: {"ok": True})

    worker._handle_transcribe(np.ones(16, dtype=np.float32), 1)

    assert saved_audio == []
    assert not (tmp_path / "last_result.txt").exists()


def test_disabled_preview_never_emits_model_or_transcript_text(
    tmp_path: Path, monkeypatch
) -> None:
    engine = FakeEngine()
    partials: list[str] = []
    worker = PipelineWorker(
        config(tmp_path, "balanced", save_last_capture=False),
        engine=engine,
        on_partial=partials.append,
    )
    monkeypatch.setattr(pipeline_worker, "trim_silence", lambda audio, *_args, **_kwargs: audio)
    monkeypatch.setattr(pipeline_worker, "postprocess_text", lambda text, *_args, **_kwargs: text)
    monkeypatch.setattr(pipeline_worker, "inject_text", lambda *_args, **_kwargs: {"ok": True})

    worker._handle_transcribe(np.ones(16, dtype=np.float32), 1)

    assert partials == []


def test_preview_setting_is_rechecked_after_settings_save(tmp_path: Path, monkeypatch) -> None:
    cfg = config(tmp_path, "balanced", save_last_capture=False)
    worker = PipelineWorker(cfg, engine=FakeEngine())
    starts: list[object] = []
    monkeypatch.setattr(worker._live, "start", starts.append)
    audio = lambda: np.ones(16, dtype=np.float32)

    cfg["live_preview"]["enabled"] = True
    worker.start_live_preview(audio)
    cfg["live_preview"]["enabled"] = False
    worker.start_live_preview(audio)

    assert starts == [audio]


def test_new_submission_cancels_older_queued_job(tmp_path: Path, monkeypatch) -> None:
    engine = FakeEngine()
    worker = PipelineWorker(config(tmp_path, "balanced"), engine=engine)
    monkeypatch.setattr(pipeline_worker, "capture_target_window", lambda: 321)

    worker.submit_audio(np.ones(16, dtype=np.float32), 1)
    first = worker._queue.get_nowait()
    worker.submit_audio(np.ones(16, dtype=np.float32), 2)
    second = worker._queue.get_nowait()

    assert first.cancel_token.is_set()
    assert not second.cancel_token.is_set()
    assert second.target_window == 321


def test_result_text_is_private_by_default(tmp_path: Path, monkeypatch, caplog) -> None:
    engine = FakeEngine()
    engine.loaded = True
    cfg = config(tmp_path, "balanced", save_last_capture=False)
    cfg["recording"]["save_last_result"] = False
    worker = PipelineWorker(cfg, engine=engine)
    monkeypatch.setattr(pipeline_worker, "trim_silence", lambda audio, *_args, **_kwargs: audio)
    monkeypatch.setattr(pipeline_worker, "postprocess_text", lambda *_args, **_kwargs: "隐私识别正文")
    monkeypatch.setattr(
        pipeline_worker,
        "inject_text",
        lambda *_args, **_kwargs: {"ok": True, "method": "ctrl_v", "error": None},
    )

    with caplog.at_level(logging.INFO):
        worker._handle_transcribe(np.ones(16, dtype=np.float32), 1)

    assert not (tmp_path / "last_result.txt").exists()
    assert "隐私识别正文" not in caplog.text


def test_recording_start_keeps_original_target_when_focus_changes(tmp_path: Path, monkeypatch) -> None:
    engine = FakeEngine()
    worker = PipelineWorker(config(tmp_path, "balanced"), engine=engine)
    foreground = {"window": 111}
    monkeypatch.setattr(
        pipeline_worker,
        "capture_target_window",
        lambda: foreground["window"],
    )

    worker.start_live_preview(lambda: np.ones(16, dtype=np.float32))
    foreground["window"] = 222
    worker.submit_audio(np.ones(16, dtype=np.float32), 1)
    job = worker._queue.get_nowait()

    assert job.target_window == 111


def test_cancel_during_final_preview_prevents_injection(tmp_path: Path, monkeypatch) -> None:
    engine = FakeEngine()
    engine.loaded = True
    cancel_token = pipeline_worker.threading.Event()
    injected: list[str] = []
    cfg = config(tmp_path, "balanced")
    cfg["live_preview"]["enabled"] = True
    worker = PipelineWorker(
        cfg,
        engine=engine,
        on_partial=lambda _text: cancel_token.set(),
    )
    monkeypatch.setattr(pipeline_worker, "trim_silence", lambda audio, *_args, **_kwargs: audio)
    monkeypatch.setattr(pipeline_worker, "postprocess_text", lambda *_args, **_kwargs: "旧任务结果")
    monkeypatch.setattr(
        pipeline_worker,
        "inject_text",
        lambda text, *_args, **_kwargs: injected.append(text) or {"ok": True},
    )

    worker._handle_transcribe(
        np.ones(16, dtype=np.float32),
        1,
        cancel_token=cancel_token,
    )

    assert injected == []


def test_cancelled_result_is_not_persisted(tmp_path: Path, monkeypatch) -> None:
    engine = FakeEngine()
    engine.loaded = True
    cfg = config(tmp_path, "balanced", save_last_capture=False)
    cfg["recording"]["save_last_result"] = True
    cancel_token = pipeline_worker.threading.Event()
    worker = PipelineWorker(cfg, engine=engine)
    monkeypatch.setattr(pipeline_worker, "trim_silence", lambda audio, *_args, **_kwargs: audio)

    def cancel_during_postprocess(*_args, **_kwargs):
        cancel_token.set()
        return "不应保存"

    monkeypatch.setattr(pipeline_worker, "postprocess_text", cancel_during_postprocess)

    worker._handle_transcribe(
        np.ones(16, dtype=np.float32),
        1,
        cancel_token=cancel_token,
    )

    assert not (tmp_path / "last_result.txt").exists()


def test_process_engine_transcription_does_not_eagerly_load_punctuation(monkeypatch) -> None:
    engine = ProcessAsrEngine({}, idle_unload_seconds=1)
    load_calls: list[bool] = []
    monkeypatch.setattr(engine, "load", lambda *, load_punctuation=True: load_calls.append(load_punctuation))
    monkeypatch.setattr(engine, "_request", lambda *_args: "结果")

    assert engine.transcribe(np.ones(16, dtype=np.float32)) == "结果"
    assert load_calls == [False]
