from __future__ import annotations

import copy
import logging
import os
import stat
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import yaml

from app.postprocess.terminology import load_terminology
from app.hotkey.keys import normalize_key, validate_hotkey_pair
from app.safe_delete import delete_file_by_verified_handle


logger = logging.getLogger(__name__)
APP_NAME = "VoiceDictation"
DEFAULT_CONFIG_NAME = "config.default.yaml"
USER_CONFIG_NAME = "config.yaml"
LOG_RETENTION_DAYS = {1, 3, 7, 30}
DEFAULT_MODELS_SUBDIR = "models"
DEFAULT_LOG_SUBDIR = "logs"
LOG_FILE_SUFFIXES = frozenset({".log", ".wav"})
LEGACY_PRIVATE_FILES = ("last_capture.wav", "last_result.txt")
DEFAULT_HOTKEY = {"primary": "right alt", "secondary": "mouse3"}
_CONFIG_WRITE_LOCK = threading.Lock()


def app_root() -> Path:
    source = sys.executable if getattr(sys, "frozen", False) else __file__
    return Path(source).resolve().parent if getattr(sys, "frozen", False) else Path(source).resolve().parents[1]


def default_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) / APP_NAME if base else Path.home() / f".{APP_NAME.lower()}"


def canonical_user_config() -> Path:
    return default_data_dir() / USER_CONFIG_NAME


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8-sig") as handle:
        value = yaml.safe_load(handle) or {}
    if not isinstance(value, dict):
        raise ValueError(f"Config must be a mapping: {path}")
    return value


def normalize_retention_days(value: Any) -> int | None:
    if value in (None, "never", 0, "0"):
        return None
    try:
        days = int(value)
    except (TypeError, ValueError):
        return 7
    return days if days in LOG_RETENTION_DAYS else 7


def _validated_logs_root(directory: Path, data_root: Path | None) -> Path:
    root = directory.resolve()
    if data_root is not None and root != data_root.resolve() / DEFAULT_LOG_SUBDIR:
        raise ValueError(f"Unsafe logs directory: {root}")
    if directory.exists() or directory.is_symlink():
        attributes = getattr(directory.lstat(), "st_file_attributes", 0)
        if directory.is_symlink() or attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError(f"Unsafe logs directory: {directory}")
    return root


def _remove_legacy_private_files(directory: Path, data_root: Path) -> None:
    root = _validated_logs_root(directory, data_root)
    for filename in LEGACY_PRIVATE_FILES:
        try:
            delete_file_by_verified_handle(
                directory / filename,
                root / filename,
            )
        except OSError as exc:
            logger.warning("Failed to remove legacy private file %s: %s", filename, exc)


def cleanup_logs(directory: Path, retention_days: int | None, data_root: Path | None = None) -> int:
    root = _validated_logs_root(directory, data_root)
    if retention_days is None or not directory.is_dir():
        return 0
    cutoff = time.time() - retention_days * 86400
    removed = 0
    for path in directory.iterdir():
        try:
            resolved = path.resolve()
            removable = path.suffix.lower() in LOG_FILE_SUFFIXES and path.name != "app.log"
            if path.is_file() and resolved.parent == root and removable and path.stat().st_mtime < cutoff:
                if delete_file_by_verified_handle(path, root / path.name):
                    removed += 1
        except OSError as exc:
            logger.warning("Failed to clean log file %s: %s", path, exc)
    return removed


def _resolve_data_dir(root: Path, configured: Any) -> Path:
    directory = Path(configured or default_data_dir())
    return directory.resolve() if directory.is_absolute() else (root / directory).resolve()


def _safe_subdir(value: Any, default: str) -> Path:
    candidate = Path(str(value or default))
    if candidate.is_absolute() or candidate.anchor or ".." in candidate.parts:
        return Path(default)
    return candidate


def _user_config_path(root: Path, config: dict[str, Any], user_path: Path | None) -> Path:
    if user_path is not None:
        return Path(user_path)
    portable = root / USER_CONFIG_NAME
    if portable.is_file():
        return portable
    paths = config.get("paths", {})
    return _resolve_data_dir(root, paths.get("data_dir")) / USER_CONFIG_NAME


def load_config(user_path: Path | None = None) -> dict[str, Any]:
    root = app_root()
    config = _load_yaml(root / DEFAULT_CONFIG_NAME)
    selected_user_config = _user_config_path(root, config, user_path)
    config = _deep_merge(config, _load_yaml(selected_user_config))

    data_dir = _resolve_data_dir(root, config.get("paths", {}).get("data_dir"))
    data_dir.mkdir(parents=True, exist_ok=True)
    paths = config.setdefault("paths", {})
    models_subdir = _safe_subdir(paths.get("models_subdir"), DEFAULT_MODELS_SUBDIR)
    log_subdir = _safe_subdir(paths.get("log_subdir"), DEFAULT_LOG_SUBDIR)
    if log_subdir != Path(DEFAULT_LOG_SUBDIR):
        log_subdir = Path(DEFAULT_LOG_SUBDIR)
    paths["app_root"] = str(root)
    paths["data_dir"] = str(data_dir)
    paths["models_subdir"] = models_subdir.as_posix()
    paths["log_subdir"] = log_subdir.as_posix()
    paths["models_dir"] = str(data_dir / models_subdir)
    paths["logs_dir"] = str(data_dir / log_subdir)
    paths["user_config"] = str(selected_user_config)
    Path(paths["logs_dir"]).mkdir(parents=True, exist_ok=True)

    recording = config.setdefault("recording", {})
    recording["save_last_capture"] = False
    recording["save_last_result"] = False
    config.setdefault("logging", {})["include_transcript_text"] = False
    _remove_legacy_private_files(Path(paths["logs_dir"]), data_dir)

    hotkey = config.setdefault("hotkey", {})
    primary = normalize_key(str(hotkey.get("primary", "right alt")))
    secondary = normalize_key(str(hotkey.get("secondary", "mouse3")))
    if validate_hotkey_pair(primary, secondary):
        hotkey.update(DEFAULT_HOTKEY)
        save_user_config_patch({"hotkey": DEFAULT_HOTKEY}, config)
    else:
        hotkey.update({"primary": primary, "secondary": secondary})
    cleanup_logs(
        Path(paths["logs_dir"]),
        normalize_retention_days(config.get("logging", {}).get("retention_days", 7)),
        data_dir,
    )

    terminology = config.setdefault("terminology", {})
    if terminology.get("enabled", True):
        builtin_file = root / terminology.get("builtin_file", "resources/ai_terms.yaml")
        user_file = data_dir / terminology.get("user_file", "terminology.yaml")
        try:
            terminology["terms"] = load_terminology(
                builtin_file,
                user_file,
                data_dir / "terminology",
            )
        except (OSError, ValueError, yaml.YAMLError) as exc:
            logger.warning("Terminology file invalid; using built-in terms: %s", exc)
            terminology["terms"] = load_terminology(builtin_file)
        terminology["builtin_path"] = str(builtin_file)
        terminology["user_path"] = str(user_file)
    return config


def models_dir(cfg: dict[str, Any]) -> Path:
    return Path(cfg["paths"]["models_dir"])


def logs_dir(cfg: dict[str, Any]) -> Path:
    return Path(cfg["paths"]["logs_dir"])


def save_user_config_patch(
    patch: dict[str, Any], cfg: dict[str, Any] | None = None
) -> Path:
    path = Path(cfg["paths"]["user_config"]) if cfg else canonical_user_config()
    with _CONFIG_WRITE_LOCK:
        merged = _deep_merge(_load_yaml(path), patch)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.stem}-", suffix=".tmp", dir=path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                yaml.safe_dump(merged, handle, allow_unicode=True, sort_keys=False)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        verified = _load_yaml(path)
        if _deep_merge(verified, {}) != merged:
            raise OSError("Configuration verification failed")
    return path


def update_runtime_config(cfg: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(cfg.get(key), dict):
            update_runtime_config(cfg[key], value)
        else:
            cfg[key] = copy.deepcopy(value)
    return cfg
