from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable


REQUIRED_PATHS = (
    "VoiceDictation.exe",
    "config.yaml",
    "_internal/python312.dll",
    "_internal/VCRUNTIME140.dll",
    "_internal/VCRUNTIME140_1.dll",
    "_internal/ucrtbase.dll",
    "_internal/_sounddevice_data/portaudio-binaries/libportaudio64bit.dll",
    "data/models/sense-voice-int8/model.int8.onnx",
    "data/models/sense-voice-int8/tokens.txt",
    "data/models/punct-ct-transformer-int8/model.int8.onnx",
    "data/models/punct-ct-transformer-int8/tokens.json",
    "data/models/silero_vad.onnx",
    "resources/ai_terms.yaml",
    "resources/VoiceDictation.ico",
    "resources/startup.wav",
    "LICENSE_OR_TERMS_ZH.txt",
    "ThirdPartyLicenses/THIRD_PARTY_NOTICES.txt",
)


def validate_portable_tree(root: Path) -> list[str]:
    return [relative for relative in REQUIRED_PATHS if not (root / relative).is_file()]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def delivery_files(root: Path, output: Path) -> tuple[str, ...]:
    return tuple(
        path.relative_to(root).as_posix()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.resolve() != output.resolve()
    )


def write_manifest(
    root: Path,
    output: Path,
    relative_paths: Iterable[str] | None = None,
) -> None:
    paths = tuple(relative_paths) if relative_paths is not None else delivery_files(root, output)
    lines = [f"{sha256_file(root / relative)} *{relative}" for relative in paths]
    output.write_text("\n".join(lines) + "\n", encoding="ascii")


def validate_manifest(root: Path, manifest: Path) -> list[str]:
    errors: list[str] = []
    listed: set[str] = set()
    for line in manifest.read_text(encoding="ascii").splitlines():
        expected, separator, relative = line.partition(" *")
        if not separator or not relative:
            errors.append("invalid manifest line")
            continue
        listed.add(relative)
        path = root / relative
        if not path.is_file():
            errors.append(f"{relative}: missing")
        elif sha256_file(path) != expected:
            errors.append(f"{relative}: hash mismatch")
    unlisted = set(delivery_files(root, manifest)) - listed
    errors.extend(f"{relative}: unlisted" for relative in sorted(unlisted))
    return errors
