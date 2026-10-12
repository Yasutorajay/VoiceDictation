from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from app.asr.engine import AsrEngine


def test_tokens_use_ascii_relative_path_under_chinese_root(
    monkeypatch, tmp_path: Path
) -> None:
    app_root = tmp_path / "临时文件" / "VoiceDictation-portable"
    model_dir = app_root / "data" / "models" / "sense-voice-int8"
    model_dir.mkdir(parents=True)
    (model_dir / "model.int8.onnx").write_bytes(b"model")
    (model_dir / "tokens.txt").write_text("token", encoding="utf-8")
    received: dict[str, str] = {}

    class OfflineRecognizer:
        @staticmethod
        def from_sense_voice(**kwargs):
            received.update({key: str(value) for key, value in kwargs.items()})
            return object()

    fake_sherpa = SimpleNamespace(OfflineRecognizer=OfflineRecognizer)
    monkeypatch.setitem(sys.modules, "sherpa_onnx", fake_sherpa)
    monkeypatch.chdir(app_root)
    engine = AsrEngine(
        {
            "audio": {"sample_rate": 16000},
            "asr": {
                "model_dir": "sense-voice-int8",
                "model_file": "model.int8.onnx",
                "tokens_file": "tokens.txt",
            },
            "paths": {"models_dir": str(app_root / "data" / "models")},
            "punctuation": {"enabled": False},
        }
    )

    engine.load(load_punctuation=False)

    assert received["model"] == str(model_dir / "model.int8.onnx")
    assert received["tokens"] == "tokens.txt"


def test_tokens_path_is_independent_of_process_cwd(monkeypatch, tmp_path: Path) -> None:
    app_root = tmp_path / "中文目录" / "VoiceDictation-portable"
    model_dir = app_root / "data" / "models" / "sense-voice-int8"
    model_dir.mkdir(parents=True)
    (model_dir / "model.int8.onnx").write_bytes(b"model")
    (model_dir / "tokens.txt").write_text("token", encoding="utf-8")
    received: dict[str, str] = {}

    class OfflineRecognizer:
        @staticmethod
        def from_sense_voice(**kwargs):
            received.update({key: str(value) for key, value in kwargs.items()})
            return object()

    monkeypatch.setitem(
        sys.modules,
        "sherpa_onnx",
        SimpleNamespace(OfflineRecognizer=OfflineRecognizer),
    )
    monkeypatch.chdir(tmp_path)
    engine = AsrEngine(
        {
            "audio": {"sample_rate": 16000},
            "asr": {
                "model_dir": "sense-voice-int8",
                "model_file": "model.int8.onnx",
                "tokens_file": "tokens.txt",
            },
            "paths": {
                "app_root": str(app_root),
                "models_dir": str(app_root / "data" / "models"),
            },
            "punctuation": {"enabled": False},
        }
    )

    engine.load(load_punctuation=False)

    assert received["tokens"] == "tokens.txt"
    assert Path.cwd() == tmp_path


def test_decode_resolves_relative_tokens_from_app_root(monkeypatch, tmp_path: Path) -> None:
    app_root = tmp_path / "中文目录" / "VoiceDictation-portable"
    model_dir = app_root / "data" / "models" / "sense-voice-int8"
    model_dir.mkdir(parents=True)
    (model_dir / "model.int8.onnx").write_bytes(b"model")
    (model_dir / "tokens.txt").write_text("token", encoding="utf-8")
    seen_cwd: list[Path] = []

    class Stream:
        result = SimpleNamespace(text="识别成功")

        def accept_waveform(self, _sample_rate, _audio):
            return None

    class Recognizer:
        def create_stream(self):
            return Stream()

        def decode_stream(self, _stream):
            seen_cwd.append(Path.cwd())

    class OfflineRecognizer:
        @staticmethod
        def from_sense_voice(**_kwargs):
            return Recognizer()

    monkeypatch.setitem(
        sys.modules,
        "sherpa_onnx",
        SimpleNamespace(OfflineRecognizer=OfflineRecognizer),
    )
    monkeypatch.chdir(tmp_path)
    engine = AsrEngine(
        {
            "audio": {"sample_rate": 16000},
            "asr": {
                "model_dir": "sense-voice-int8",
                "model_file": "model.int8.onnx",
                "tokens_file": "tokens.txt",
            },
            "paths": {
                "app_root": str(app_root),
                "models_dir": str(app_root / "data" / "models"),
            },
            "punctuation": {"enabled": False},
        }
    )

    engine.load(load_punctuation=False)
    text = engine.transcribe(np.ones(160, dtype=np.float32))

    assert text == "识别成功"
    assert seen_cwd == [model_dir]
    assert Path.cwd() == tmp_path


def test_tokens_support_external_chinese_models_directory(monkeypatch, tmp_path: Path) -> None:
    app_root = tmp_path / "VoiceDictation-portable"
    model_dir = tmp_path / "外置中文数据" / "模型" / "sense-voice-int8"
    model_dir.mkdir(parents=True)
    app_root.mkdir()
    (model_dir / "model.int8.onnx").write_bytes(b"model")
    (model_dir / "tokens.txt").write_text("token", encoding="utf-8")
    received: dict[str, str] = {}
    seen_cwd: list[Path] = []

    class OfflineRecognizer:
        @staticmethod
        def from_sense_voice(**kwargs):
            received.update({key: str(value) for key, value in kwargs.items()})
            seen_cwd.append(Path.cwd())
            return object()

    monkeypatch.setitem(
        sys.modules,
        "sherpa_onnx",
        SimpleNamespace(OfflineRecognizer=OfflineRecognizer),
    )
    monkeypatch.chdir(tmp_path)
    engine = AsrEngine(
        {
            "audio": {"sample_rate": 16000},
            "asr": {
                "model_dir": "sense-voice-int8",
                "model_file": "model.int8.onnx",
                "tokens_file": "tokens.txt",
            },
            "paths": {
                "app_root": str(app_root),
                "models_dir": str(model_dir.parent),
            },
            "punctuation": {"enabled": False},
        }
    )

    engine.load(load_punctuation=False)

    assert received["tokens"] == "tokens.txt"
    assert seen_cwd == [model_dir]
    assert Path.cwd() == tmp_path
