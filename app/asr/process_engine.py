from __future__ import annotations

import logging
import multiprocessing
import threading
import time
from multiprocessing.connection import Connection
from typing import Any

import numpy as np

from app.asr.engine import AsrEngine

logger = logging.getLogger(__name__)
REQUEST_TIMEOUT_SECONDS = 180.0


def _engine_process(connection: Connection, cfg: dict[str, Any]) -> None:
    engine = AsrEngine(cfg)
    try:
        while True:
            command, payload = connection.recv()
            try:
                if command == "load":
                    engine.load(load_punctuation=bool(payload))
                    result = None
                elif command == "transcribe":
                    result = engine.transcribe(payload)
                elif command == "punctuate":
                    result = engine.punctuate(str(payload))
                elif command == "close":
                    connection.send((True, None))
                    return
                else:
                    raise ValueError(f"Unknown engine command: {command}")
                connection.send((True, result))
            except Exception as exc:
                logger.exception("recognition subprocess command failed")
                connection.send((False, f"{type(exc).__name__}: {exc}"))
    except EOFError:
        return
    finally:
        engine.close()
        connection.close()


class ProcessAsrEngine:
    def __init__(self, cfg: dict[str, Any], *, idle_unload_seconds: int) -> None:
        self.cfg = cfg
        self._idle_unload_seconds = idle_unload_seconds
        self._process: multiprocessing.Process | None = None
        self._connection: Connection | None = None
        self._request_lock = threading.Lock()
        self._last_used = 0.0
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded and self._process is not None and self._process.is_alive()

    def load(self, *, load_punctuation: bool = True) -> None:
        if self.is_loaded:
            return
        with self._request_lock:
            if self.is_loaded:
                return
            if self._process is not None:
                self.close()
            self._start_process()
            try:
                self._request_unlocked("load", load_punctuation)
            except Exception:
                self.close()
                raise
            self._loaded = True
            self._last_used = time.monotonic()

    def transcribe(self, audio: np.ndarray) -> str:
        self.load(load_punctuation=False)
        return str(self._request("transcribe", audio))

    def punctuate(self, text: str) -> str:
        if not text:
            return text
        self.load(load_punctuation=True)
        return str(self._request("punctuate", text))

    def release_if_idle(self) -> None:
        if not self.is_loaded or self._idle_unload_seconds <= 0:
            return
        if time.monotonic() - self._last_used >= self._idle_unload_seconds:
            logger.info("Unloading low-memory recognition subprocess after idle timeout")
            self.close()

    def close(self) -> None:
        process = self._process
        connection = self._connection
        self._loaded = False
        self._process = None
        self._connection = None
        if process is None:
            return
        if process.is_alive() and connection is not None:
            try:
                connection.send(("close", None))
                if connection.poll(2.0):
                    connection.recv()
            except (BrokenPipeError, EOFError, OSError):
                logger.debug("recognition subprocess closed before acknowledgement")
        process.join(timeout=2.0)
        if process.is_alive():
            process.terminate()
            process.join(timeout=2.0)
        if connection is not None:
            connection.close()

    def _start_process(self) -> None:
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe()
        process = context.Process(
            target=_engine_process,
            args=(child, self.cfg),
            name="voice-recognition",
            daemon=True,
        )
        process.start()
        child.close()
        self._process = process
        self._connection = parent

    def _request(self, command: str, payload: Any) -> Any:
        with self._request_lock:
            result = self._request_unlocked(command, payload)
            self._last_used = time.monotonic()
            return result

    def _request_unlocked(self, command: str, payload: Any) -> Any:
        connection = self._connection
        if connection is None:
            raise RuntimeError("Recognition subprocess is not running")
        connection.send((command, payload))
        if not connection.poll(REQUEST_TIMEOUT_SECONDS):
            self.close()
            raise TimeoutError("Recognition subprocess timed out")
        ok, result = connection.recv()
        if not ok:
            raise RuntimeError(result)
        return result
