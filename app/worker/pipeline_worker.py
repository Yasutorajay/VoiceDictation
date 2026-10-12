from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable

import numpy as np

from app.asr.engine import AsrEngine
from app.asr.process_engine import ProcessAsrEngine
from app.audio.capture import trim_silence
from app.inject.clipboard_inject import capture_target_window, inject_text
from app.postprocess.pipeline import postprocess_text
from app.performance import resolve_performance_profile
from app.worker.live_preview import LivePreview

logger = logging.getLogger(__name__)


class JobKind(Enum):
    TRANSCRIBE = auto()
    SHUTDOWN = auto()


@dataclass
class Job:
    kind: JobKind
    audio: np.ndarray | None = None
    duration_ms: int = 0
    cancel_token: threading.Event = field(default_factory=threading.Event)
    target_window: int | None = None


class PipelineWorker:
    def __init__(
        self,
        cfg: dict[str, Any],
        *,
        on_status: Callable[[str], None] | None = None,
        on_busy: Callable[[bool], None] | None = None,
        on_result: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_partial: Callable[[str], None] | None = None,
        engine: Any | None = None,
    ) -> None:
        self.cfg = cfg
        self._on_status = on_status or (lambda _s: None)
        self._on_busy = on_busy or (lambda _b: None)
        self._on_result = on_result or (lambda _t: None)
        self._on_error = on_error or (lambda _e: None)
        self._on_partial = on_partial or (lambda _t: None)
        self._queue: queue.Queue[Job] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._profile = resolve_performance_profile(cfg)
        self._engine = engine or self._create_engine()
        self._job_lock = threading.Lock()
        self._latest_cancel_token: threading.Event | None = None
        self._recording_target_window: int | None = None
        performance_cfg = cfg.get("performance", {})
        self._use_model_punctuation = not self._profile.use_subprocess or bool(
            performance_cfg.get("low_memory_model_punctuation", False)
        )
        live_cfg = cfg.get("live_preview", {})
        self._live = LivePreview(
            self._engine,
            sample_rate=int(cfg.get("audio", {}).get("sample_rate", 16000)),
            interval_ms=int(live_cfg.get("interval_ms", 250)),
            min_audio_ms=int(live_cfg.get("min_audio_ms", 250)),
            max_audio_ms=int(live_cfg.get("max_audio_ms", 6000)),
            on_partial=self._on_partial,
        )

    @property
    def engine(self) -> AsrEngine:
        return self._engine

    def start(self) -> None:
        if self._profile.load_main_on_start:
            self._engine.load(
                load_punctuation=self._profile.load_punctuation_on_start
            )
        self._thread = threading.Thread(
            target=self._loop, name="pipeline-worker", daemon=True
        )
        self._thread.start()

    def start_live_preview(self, get_audio: Callable[[], np.ndarray]) -> None:
        with self._job_lock:
            self._recording_target_window = capture_target_window()
        if not self._preview_enabled():
            return
        self._live.start(get_audio)

    def _preview_enabled(self) -> bool:
        configured = bool(self.cfg.get("live_preview", {}).get("enabled", False))
        return configured and not self._profile.use_subprocess

    def stop_live_preview(self) -> None:
        self._live.stop()

    def submit_audio(
        self,
        audio: np.ndarray,
        duration_ms: int,
        target_window: int | None = None,
    ) -> None:
        self.stop_live_preview()
        cancel_token = threading.Event()
        with self._job_lock:
            recorded_target = self._recording_target_window
            self._recording_target_window = None
            if self._latest_cancel_token is not None:
                self._latest_cancel_token.set()
            self._latest_cancel_token = cancel_token
        resolved_target = target_window if target_window is not None else recorded_target
        if resolved_target is None:
            resolved_target = capture_target_window()
        self._queue.put(
            Job(
                JobKind.TRANSCRIBE,
                audio=audio,
                duration_ms=duration_ms,
                cancel_token=cancel_token,
                target_window=resolved_target,
            )
        )

    def cancel(self) -> None:
        with self._job_lock:
            if self._latest_cancel_token is not None:
                self._latest_cancel_token.set()
            self._recording_target_window = None
        self.stop_live_preview()

    def shutdown(self) -> None:
        self.stop_live_preview()
        self.cancel()
        self._queue.put(Job(JobKind.SHUTDOWN))
        if self._thread:
            self._thread.join(timeout=5)
        self._engine.close()

    def _loop(self) -> None:
        while True:
            try:
                job = self._queue.get(timeout=1.0)
            except queue.Empty:
                self._engine.release_if_idle()
                continue
            if job.kind == JobKind.SHUTDOWN:
                break
            if job.kind == JobKind.TRANSCRIBE and job.audio is not None:
                self._handle_transcribe(
                    job.audio,
                    job.duration_ms,
                    cancel_token=job.cancel_token,
                    target_window=job.target_window,
                )

    def _handle_transcribe(
        self,
        audio: np.ndarray,
        duration_ms: int,
        *,
        cancel_token: threading.Event | None = None,
        target_window: int | None = None,
    ) -> None:
        job_cancelled = cancel_token or threading.Event()
        self._on_busy(True)
        self._on_status("processing")
        t0 = time.perf_counter()
        try:
            if job_cancelled.is_set():
                self._on_status("cancelled")
                return

            if not self._engine.is_loaded:
                if self._preview_enabled():
                    self._on_partial("正在初始化语音模型…")
                self._engine.load(
                    load_punctuation=self._profile.load_punctuation_on_start
                )

            audio_cfg = self.cfg.get("audio", {})
            trimmed = trim_silence(
                audio,
                int(audio_cfg.get("sample_rate", 16000)),
                silence_rms=float(audio_cfg.get("silence_rms", 0.008)),
                pad_ms=int(audio_cfg.get("pad_ms", 120)),
            )
            if trimmed.size == 0:
                logger.info("empty audio after trim; skip")
                self._on_status("idle")
                return

            t_asr0 = time.perf_counter()
            raw = self._engine.transcribe(trimmed)
            asr_ms = int((time.perf_counter() - t_asr0) * 1000)

            if job_cancelled.is_set():
                self._on_status("cancelled")
                return

            t_pp0 = time.perf_counter()
            text = postprocess_text(
                raw,
                self.cfg,
                model_punctuate=(
                    self._engine.punctuate if self._use_model_punctuation else None
                ),
            )
            pp_ms = int((time.perf_counter() - t_pp0) * 1000)

            if job_cancelled.is_set():
                self._on_status("cancelled")
                return

            if not text:
                logger.info("empty transcript after postprocess")
                self._on_status("idle")
                return

            if job_cancelled.is_set():
                self._on_status("cancelled")
                return

            if self._preview_enabled():
                self._on_partial(text)
            if job_cancelled.is_set():
                self._on_status("cancelled")
                return

            t_inj0 = time.perf_counter()
            result = inject_text(
                text,
                self.cfg,
                target_window=target_window,
                cancelled=job_cancelled.is_set,
                input_gate=self._job_lock,
            )
            inj_ms = int((time.perf_counter() - t_inj0) * 1000)
            total_ms = int((time.perf_counter() - t0) * 1000)

            logger.info(
                "job done audio_ms=%d asr_ms=%d pp_ms=%d inj_ms=%d total_ms=%d chars=%d ok=%s",
                duration_ms,
                asr_ms,
                pp_ms,
                inj_ms,
                total_ms,
                len(text),
                result.get("ok"),
            )
            self._on_result(text)
            if result.get("ok"):
                self._on_status("done")
            else:
                self._on_error(result.get("error") or "inject failed")
        except Exception as exc:
            logger.exception("pipeline failed")
            self._on_error(str(exc))
        finally:
            with self._job_lock:
                if self._latest_cancel_token is job_cancelled:
                    self._latest_cancel_token = None
            self._on_busy(False)

    def _create_engine(self) -> Any:
        if self._profile.use_subprocess:
            return ProcessAsrEngine(
                self.cfg,
                idle_unload_seconds=self._profile.idle_unload_seconds,
            )
        return AsrEngine(self.cfg)
