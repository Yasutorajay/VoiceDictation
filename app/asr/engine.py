from __future__ import annotations

import logging
import os
import threading
import gc
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import numpy as np

logger = logging.getLogger(__name__)
_MODEL_LOAD_LOCK = threading.Lock()


@contextmanager
def _app_working_directory(root: Path) -> Iterator[None]:
    with _MODEL_LOAD_LOCK:
        original_cwd = Path.cwd()
        try:
            os.chdir(root)
            yield
        finally:
            os.chdir(original_cwd)


def _sherpa_tokens_path(tokens_path: Path) -> str:
    filename = tokens_path.name
    return filename if filename.isascii() else str(tokens_path)


class AsrEngine:
    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg
        self._recognizer = None
        self._punctuator = None
        self._punctuation_attempted = False
        self._decode_lock = threading.Lock()
        self._load_lock = threading.Lock()
        self.sample_rate = int(cfg.get("audio", {}).get("sample_rate", 16000))
        paths = cfg.get("paths", {})
        models_dir = paths.get("models_dir")
        inferred_root = Path(models_dir).parents[1] if models_dir else Path.cwd()
        self._app_root = Path(paths.get("app_root") or inferred_root)
        self._tokens_root = self._app_root

    @property
    def is_loaded(self) -> bool:
        return self._recognizer is not None

    def load(self, *, load_punctuation: bool = True) -> None:
        with self._load_lock:
            self._load_unlocked(load_punctuation=load_punctuation)

    def _load_unlocked(self, *, load_punctuation: bool) -> None:
        if self._recognizer is not None:
            if load_punctuation:
                self._load_punctuation(Path(self.cfg["paths"]["models_dir"]))
            return
        import sherpa_onnx
        asr = self.cfg["asr"]
        models = Path(self.cfg["paths"]["models_dir"])
        model_dir = models / asr.get("model_dir", "sense-voice-int8")
        model_path = model_dir / asr.get("model_file", "model.int8.onnx")
        tokens_path = model_dir / asr.get("tokens_file", "tokens.txt")
        if not model_path.is_file() or not tokens_path.is_file():
            raise FileNotFoundError(f"ASR model not found under {model_dir}")
        self._tokens_root = tokens_path.parent
        language = str(asr.get("language") or "auto")
        logger.info("Loading SenseVoice: %s (provider=%s, language=%s)", model_path, asr.get("provider", "cpu"), language)
        with _app_working_directory(self._tokens_root):
            self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=str(model_path), tokens=_sherpa_tokens_path(tokens_path),
                num_threads=int(asr.get("num_threads", 4)), sample_rate=self.sample_rate,
                feature_dim=80, provider=str(asr.get("provider", "cpu")),
                language=language, use_itn=bool(asr.get("use_itn", True)),
            )
        logger.info("ASR model loaded")
        if load_punctuation and self.cfg.get("punctuation", {}).get("enabled", True):
            self._load_punctuation(models)

    def _load_punctuation(self, models: Path) -> None:
        if self._punctuator is not None or self._punctuation_attempted:
            return
        self._punctuation_attempted = True
        import sherpa_onnx
        pcfg = self.cfg.get("punctuation", {})
        pdir = models / pcfg.get("model_dir", "punct-ct-transformer-int8")
        candidates = list(pdir.glob("*.onnx"))
        if not candidates:
            return
        try:
            self._punctuator = sherpa_onnx.OfflinePunctuation(sherpa_onnx.OfflinePunctuationConfig(
                model=sherpa_onnx.OfflinePunctuationModelConfig(
                    ct_transformer=str(candidates[0]),
                    num_threads=int(self.cfg.get("asr", {}).get("num_threads", 2)),
                    provider=str(self.cfg.get("asr", {}).get("provider", "cpu")),
                )))
            logger.info("Punctuation model loaded: %s", candidates[0])
        except Exception:
            logger.exception("Failed to load punctuation model")

    def transcribe(self, audio: np.ndarray) -> str:
        if self._recognizer is None or audio.size == 0:
            return ""
        with self._decode_lock:
            with _app_working_directory(self._tokens_root):
                stream = self._recognizer.create_stream()
                stream.accept_waveform(self.sample_rate, audio)
                self._recognizer.decode_stream(stream)
                return (stream.result.text or "").strip()

    def punctuate(self, text: str) -> str:
        if not text or not self.cfg.get("punctuation", {}).get("enabled", True):
            return text
        if self._punctuator is None:
            with self._load_lock:
                self._load_punctuation(Path(self.cfg["paths"]["models_dir"]))
        if self._punctuator is None:
            return text
        try:
            return self._punctuator.add_punctuation(text)
        except Exception:
            logger.exception("punctuation failed")
            return text

    def release_if_idle(self) -> None:
        return None

    def close(self) -> None:
        with self._load_lock:
            self._punctuator = None
            self._recognizer = None
            self._punctuation_attempted = False
        gc.collect()
