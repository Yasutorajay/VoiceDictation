from __future__ import annotations

import logging
import threading
import time
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class AudioCapture:
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        device: Any = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.device = device
        self._stream = None
        self._lock = threading.Lock()
        self._chunks: list[np.ndarray] = []
        self._recording = False
        self._started_at = 0.0
        self._level = 0.0
        self._bands = [0.08] * 28

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start(self) -> None:
        import sounddevice as sd

        with self._lock:
            self._recording = True
            self._chunks = []
            self._started_at = time.monotonic()

        def callback(indata, frames, time_info, status) -> None:  # noqa: ARG001
            if status:
                logger.debug("audio status: %s", status)
            if not self._recording:
                return
            mono = indata.copy()
            if mono.ndim > 1:
                mono = mono.mean(axis=1, keepdims=True)
            samples = mono.reshape(-1).astype(np.float32)
            bands, level = _waveform_bands(samples, n_bands=28)
            alpha = 0.45
            with self._lock:
                self._chunks.append(samples)
                self._level = level
                self._bands = [
                    alpha * band + (1.0 - alpha) * old
                    for band, old in zip(bands, self._bands)
                ]

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            device=self.device,
            dtype="float32",
            callback=callback,
        )
        self._stream.start()
        logger.info(
            "Audio capture started: %s Hz, channels=%s, device=%s",
            self.sample_rate,
            self.channels,
            self.device,
        )

    def snapshot(self) -> np.ndarray:
        """Copy of audio captured so far (safe for concurrent preview ASR)."""
        with self._lock:
            if not self._chunks:
                return np.zeros(0, dtype=np.float32)
            return np.concatenate(self._chunks).astype(np.float32)

    def levels(self) -> list[float]:
        with self._lock:
            return list(self._bands)

    def level(self) -> float:
        with self._lock:
            return float(self._level)

    def stop(self) -> np.ndarray:
        with self._lock:
            self._recording = False
            stream = self._stream
            self._stream = None
            chunks = list(self._chunks)
            self._chunks = []
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                logger.exception("error closing audio stream")
        if not chunks:
            audio = np.zeros(0, dtype=np.float32)
        else:
            audio = np.concatenate(chunks).astype(np.float32)
        elapsed = max(0.0, time.monotonic() - self._started_at)
        logger.info(
            "Audio capture stopped: %.2fs, %d samples",
            elapsed,
            int(audio.shape[0]),
        )
        return audio

    def cancel(self) -> None:
        self.stop()


def _waveform_bands(samples: np.ndarray, n_bands: int = 28) -> tuple[list[float], float]:
    if samples.size == 0:
        return ([0.08] * n_bands, 0.0)
    rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2) + 1e-12))
    level = max(0.0, min(1.0, rms * 14))
    chunk = max(1, samples.size // n_bands)
    bands: list[float] = []
    for i in range(n_bands):
        seg = samples[i * chunk : (i + 1) * chunk]
        if seg.size == 0:
            bands.append(0.08)
            continue
        s_rms = float(np.sqrt(np.mean(seg.astype(np.float64) ** 2) + 1e-12))
        bands.append(max(0.05, min(1.0, s_rms * 16)))
    return (bands, level)


def trim_silence(
    audio: np.ndarray,
    sample_rate: int,
    *,
    silence_rms: float = 0.01,
    pad_ms: int = 120,
    frame_ms: int = 20,
) -> np.ndarray:
    if audio.size == 0:
        return audio
    frame = max(1, int(sample_rate * frame_ms / 1000))
    n_frames = audio.size // frame
    if n_frames == 0:
        return audio
    frames = audio[: n_frames * frame].reshape(n_frames, frame)
    rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)
    active = rms > silence_rms
    if not np.any(active):
        return audio[:0]
    first = int(np.argmax(active))
    last = int(len(active) - 1 - np.argmax(active[::-1]))
    pad = int(sample_rate * pad_ms / 1000)
    start = max(0, first * frame - pad)
    end = min(audio.size, (last + 1) * frame + pad)
    return audio[start:end]


def save_wav(path: Any, audio: np.ndarray, sample_rate: int) -> None:
    from scipy.io import wavfile

    clipped = np.clip(audio, -1, 1)
    pcm = (clipped * 32767).astype(np.int16)
    wavfile.write(path, sample_rate, pcm)
