from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from app.audio.capture import AudioCapture
from app.config import app_root, load_config, logs_dir, save_user_config_patch, update_runtime_config
from app.hotkey.capture import OneShotHotkeyCapture
from app.hotkey.fsm import HotkeyConfig, HotkeyFSM
from app.hotkey.keys import format_chord, normalize_key, validate_hotkey_pair
from app.hotkey.listener import HotkeyListener
from app.logging_setup import setup_logging
from app.ui.about import AboutWindow
from app.ui.hotkey_settings import HotkeySettingsWindow
from app.ui.overlay import StatusOverlay
from app.ui.startup_sound import play_startup_sound
from app.ui.tray import TrayApp
from app.worker.pipeline_worker import PipelineWorker

logger = logging.getLogger(__name__)


class Application:
    def __init__(self, cfg: dict[str, Any] | None = None) -> None:
        self.cfg = cfg if cfg is not None else load_config()
        setup_logging(
            self.cfg.get("logging", {}).get("level", "INFO"),
            logs_dir(self.cfg),
        )
        self._stop_event = threading.Event()
        self._paused = False
        self._capture = AudioCapture(
            sample_rate=int(self.cfg["audio"]["sample_rate"]),
            channels=int(self.cfg["audio"]["channels"]),
            device=self.cfg["audio"].get("device"),
        )
        self._overlay = StatusOverlay()
        self._worker: PipelineWorker | None = None
        self._fsm: HotkeyFSM | None = None
        self._listener: HotkeyListener | None = None
        self._tray: TrayApp | None = None
        self._hotkey_settings: HotkeySettingsWindow | None = None
        self._about_window: AboutWindow | None = None
        self._single_instance_handle = None
        self._asr_lock = threading.Lock()
        self._level_timer: threading.Timer | None = None
        self._level_pump = False

    def _acquire_single_instance(self) -> bool:
        if os.name != "nt":
            return True
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_bool,
            ctypes.c_wchar_p,
        ]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.SetLastError(0)
        handle = kernel32.CreateMutexW(None, False, "Local\\VoiceDictationSingleton")
        last_error = ctypes.get_last_error()
        self._single_instance_handle = handle
        if handle and last_error == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel32.CloseHandle.restype = ctypes.c_bool
            kernel32.CloseHandle(handle)
            self._single_instance_handle = None
            logger.error("Another instance is already running. Close the tray icon first.")
            return False
        if not handle:
            logger.error("CreateMutex failed, error=%s", last_error)
            return False
        return True

    def run(self) -> int | None:
        if not self._acquire_single_instance():
            return 1
        logger.info("Starting VoiceDictation")
        primary = normalize_key(
            str(self.cfg["hotkey"].get("primary", "right alt"))
        )
        secondary = normalize_key(
            str(self.cfg["hotkey"].get("secondary", "mouse3"))
        )
        chord = format_chord(primary, secondary)

        self._overlay.start()
        if self.cfg.get("branding", {}).get("startup_sound", True):
            play_startup_sound(app_root() / "resources" / "startup.wav")

        self._tray = TrayApp(
            on_quit=self.stop,
            on_toggle_pause=self.toggle_pause,
            on_open_logs=self.open_logs,
            on_open_hotkey_settings=self.open_hotkey_settings,
            on_open_about=self.open_about,
            chord_label=chord,
        )
        self._tray.start()

        try:
            self._worker = PipelineWorker(
                self.cfg,
                on_status=self._on_status,
                on_busy=self._on_busy,
                on_result=self._on_result,
                on_error=self._on_error,
                on_partial=self._on_partial,
            )
            original_transcribe = self._worker.engine.transcribe

            def locked_transcribe(audio):
                with self._asr_lock:
                    return original_transcribe(audio)

            self._worker.engine.transcribe = locked_transcribe  # type: ignore[method-assign]
            self._worker.start()
        except Exception as exc:
            logger.exception("Failed to start ASR worker")
            self._overlay.show(f"模型加载失败: {exc}", mode="error")
            if self._tray:
                self._tray.set_state("error")
            self._worker = None

        hotkey_cfg = HotkeyConfig(
            primary=primary,
            secondary=secondary,
            min_hold_ms=int(self.cfg["hotkey"].get("min_hold_ms", 250)),
            cooldown_ms=int(self.cfg["hotkey"].get("cooldown_ms", 150)),
            enabled=bool(self.cfg["hotkey"].get("enabled", True)),
        )
        self._fsm = HotkeyFSM(
            hotkey_cfg,
            on_start=self._on_record_start,
            on_stop=self._on_record_stop,
            on_cancel=self._on_record_cancel,
        )
        self._listener = HotkeyListener(
            self._fsm.on_key,
            primary_key=primary,
            secondary_key=secondary,
        )
        self._listener.start()

        live_enabled = bool(self.cfg.get("live_preview", {}).get("enabled", False))
        logger.info(
            "Ready. Hold %s to dictate. Live preview enabled=%s",
            chord,
            live_enabled,
        )
        if self._tray:
            self._tray.set_state("idle")

        try:
            while not self._stop_event.is_set():
                time.sleep(0.2)
        finally:
            self._shutdown()
        return 0

    def stop(self) -> None:
        self._stop_event.set()

    def toggle_pause(self) -> None:
        self._paused = not self._paused
        if self._fsm:
            self._fsm.set_paused(self._paused)
        if self._tray:
            self._tray.set_paused(self._paused)
        if self._paused:
            if self._worker:
                self._worker.stop_live_preview()
            self._stop_level_pump()
            self._overlay.show("热键已暂停", mode="error")
            return
        self._overlay.hide()

    def open_logs(self) -> None:
        path = logs_dir(self.cfg)
        path.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
        except Exception:
            system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
            subprocess.Popen([str(system_root / "explorer.exe"), str(path)])

    def open_about(self) -> None:
        if self._about_window is not None:
            self._about_window.open()
            return

        def on_close() -> None:
            self._about_window = None

        self._about_window = AboutWindow(app_root(), on_close)
        self._about_window.open()

    def open_hotkey_settings(self) -> None:
        if self._hotkey_settings is not None:
            self._hotkey_settings.open()
            return

        primary = normalize_key(
            str(self.cfg["hotkey"].get("primary", "right alt"))
        )
        secondary = normalize_key(
            str(self.cfg["hotkey"].get("secondary", "mouse3"))
        )
        was_paused = self._paused
        if not was_paused:
            self.toggle_pause()

        active_capture: list[OneShotHotkeyCapture | None] = [None]

        def on_save(p: str, s: str) -> None:
            self.apply_hotkey(p, s)

        def on_capture(cb) -> None:
            if active_capture[0] is not None:
                active_capture[0].cancel()
            try:
                capture = OneShotHotkeyCapture(cb)
                active_capture[0] = capture
                capture.start()
            except Exception:
                logger.exception("failed to start hotkey capture")
                active_capture[0] = None
                cb("")

        def on_close() -> None:
            if active_capture[0] is not None:
                active_capture[0].cancel()
                active_capture[0] = None
            if self._paused and not was_paused:
                self.toggle_pause()
            self._hotkey_settings = None

        win = HotkeySettingsWindow(
            primary=primary,
            secondary=secondary,
            on_save=on_save,
            cfg=self.cfg,
            on_capture=on_capture,
            on_close=on_close,
        )
        self._hotkey_settings = win
        win.open()

    def apply_hotkey(self, primary: str, secondary: str) -> None:
        p = normalize_key(primary)
        s = normalize_key(secondary)
        error = validate_hotkey_pair(p, s)
        if error:
            raise ValueError(error)
        patch = {"hotkey": {"primary": p, "secondary": s}}
        save_user_config_patch(patch, self.cfg)
        update_runtime_config(self.cfg, patch)
        cfg = HotkeyConfig(
            primary=p,
            secondary=s,
            min_hold_ms=int(self.cfg["hotkey"].get("min_hold_ms", 250)),
            cooldown_ms=int(self.cfg["hotkey"].get("cooldown_ms", 150)),
            enabled=bool(self.cfg["hotkey"].get("enabled", True)),
        )
        if self._fsm:
            self._fsm.update_config(cfg)
        if self._listener:
            self._listener.set_bindings(p, s)
        if self._tray:
            self._tray.set_chord_label(p, s)
            self._tray.set_state("idle" if not self._paused else "paused")
        logger.info("Hotkey updated to %s", format_chord(p, s))

    def _on_record_start(self) -> None:
        logger.info("Recording start")
        if self._tray:
            self._tray.set_state("recording")
        if self.cfg.get("ui", {}).get("show_overlay", True):
            self._overlay.show(
                self.cfg["ui"].get("overlay_text_recording", "Listening…"),
                mode="recording",
            )
        try:
            self._capture.start()
            self._start_level_pump()
            if self._worker:
                self._worker.start_live_preview(self._capture.snapshot)
        except Exception:
            logger.exception("failed to start capture")
            self._overlay.show("麦克风打开失败", mode="error")

    def _on_record_stop(self, duration_ms: int) -> None:
        logger.info("Recording stop (%d ms)", duration_ms)
        self._stop_level_pump()
        if self._worker:
            self._worker.stop_live_preview()
        audio = self._capture.stop()
        if self._worker is None:
            return
        if self._tray:
            self._tray.set_state("processing")
        if self.cfg.get("ui", {}).get("show_overlay", True):
            self._overlay.show(
                self.cfg["ui"].get("overlay_text_processing", "Transcribing…"),
                mode="processing",
            )
        self._worker.submit_audio(audio, duration_ms)

    def _on_record_cancel(self) -> None:
        logger.info("Recording cancelled")
        self._stop_level_pump()
        if self._worker:
            self._worker.cancel()
        if self._capture.is_recording:
            self._capture.cancel()
        if self.cfg.get("ui", {}).get("show_overlay", True):
            self._overlay.show(
                self.cfg["ui"].get("overlay_text_cancelled", "Cancelled"),
                mode="error",
            )
            threading.Timer(0.8, self._overlay.hide).start()
        if self._tray:
            self._tray.set_state("idle")

    def _start_level_pump(self) -> None:
        self._level_pump = True
        self._pump_levels()

    def _stop_level_pump(self) -> None:
        self._level_pump = False
        if self._level_timer is not None:
            try:
                self._level_timer.cancel()
            except Exception:
                pass
            self._level_timer = None

    def _pump_levels(self) -> None:
        if not self._level_pump:
            return
        try:
            if self.cfg.get("ui", {}).get("show_overlay", True):
                self._overlay.set_levels(self._capture.levels())
            self._level_timer = threading.Timer(0.04, self._pump_levels)
            self._level_timer.daemon = True
            self._level_timer.start()
        except Exception:
            logger.debug("level pump failed", exc_info=True)

    def _on_partial(self, text: str) -> None:
        """Live or final text for overlay while speaking / before paste."""
        if not text:
            return
        if self.cfg.get("ui", {}).get("show_overlay", True):
            self._overlay.show_partial(text)

    def _on_status(self, status: str) -> None:
        ui = self.cfg.get("ui", {})
        mapping = {
            "processing": ui.get("overlay_text_processing", "Transcribing…"),
            "done": ui.get("overlay_text_done", "Done"),
            "cancelled": ui.get("overlay_text_cancelled", "Cancelled"),
            "idle": None,
            "error": ui.get("overlay_text_error", "Error"),
        }
        text = mapping.get(status)
        if status == "done":
            if ui.get("show_overlay", True) and text:
                self._overlay.show(text, mode="done")
            if self._tray:
                self._tray.set_state("idle")
            threading.Timer(0.9, self._overlay.hide).start()
            return
        if status in ("idle", "cancelled"):
            if text and ui.get("show_overlay", True):
                self._overlay.show(
                    text, mode="error" if status == "cancelled" else "idle"
                )
                threading.Timer(0.7, self._overlay.hide).start()
            else:
                self._overlay.hide()
            if self._tray:
                self._tray.set_state("idle")
            return
        if status == "processing":
            if self._tray:
                self._tray.set_state("processing")
            if text and ui.get("show_overlay", True):
                self._overlay.show(text, mode="processing")
            return
        if status == "error":
            if self._tray:
                self._tray.set_state("error")
            if text and ui.get("show_overlay", True):
                self._overlay.show(text, mode="error")
                threading.Timer(1.5, self._overlay.hide).start()

    def _on_busy(self, busy: bool) -> None:
        if self._fsm:
            self._fsm.set_busy(busy)

    def _on_result(self, text: str) -> None:
        logger.info("Result: %s", text)

    def _on_error(self, message: str) -> None:
        logger.error("Error: %s", message)
        self._on_status("error")
        if self.cfg.get("ui", {}).get("show_overlay", True):
            self._overlay.show(f"出错: {message[:40]}", mode="error")

    def _shutdown(self) -> None:
        logger.info("Shutting down")
        self._stop_level_pump()
        try:
            if self._listener:
                self._listener.stop()
        except Exception:
            logger.exception("listener stop")
        try:
            if self._worker:
                self._worker.stop_live_preview()
        except Exception:
            pass
        try:
            if self._capture.is_recording:
                self._capture.cancel()
        except Exception:
            pass
        try:
            if self._worker:
                self._worker.shutdown()
        except Exception:
            logger.exception("worker shutdown")
        try:
            self._overlay.stop()
        except Exception:
            pass
        try:
            if self._tray:
                self._tray.stop()
        except Exception:
            pass
        if self._single_instance_handle:
            try:
                import ctypes

                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
                kernel32.CloseHandle.restype = ctypes.c_bool
                kernel32.CloseHandle(self._single_instance_handle)
                self._single_instance_handle = None
            except Exception:
                logger.exception("single-instance handle close")
