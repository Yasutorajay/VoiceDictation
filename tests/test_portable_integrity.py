from pathlib import Path

from scripts.portable_integrity import (
    REQUIRED_PATHS,
    validate_manifest,
    validate_portable_tree,
    write_manifest,
)


def test_integrity_requires_runtime_models_and_resources(tmp_path: Path) -> None:
    missing = validate_portable_tree(tmp_path)
    assert set(missing) == set(REQUIRED_PATHS)


def test_integrity_passes_when_all_required_files_exist(tmp_path: Path) -> None:
    for relative in REQUIRED_PATHS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    assert validate_portable_tree(tmp_path) == []


def test_manifest_detects_changed_files(tmp_path: Path) -> None:
    payload = tmp_path / "payload.bin"
    payload.write_bytes(b"original")
    manifest = tmp_path / "SHA256SUMS.txt"
    write_manifest(tmp_path, manifest, ("payload.bin",))

    payload.write_bytes(b"changed")

    assert validate_manifest(tmp_path, manifest) == ["payload.bin: hash mismatch"]


def test_manifest_covers_all_delivery_files(tmp_path: Path) -> None:
    (tmp_path / "VoiceDictation.exe").write_bytes(b"exe")
    (tmp_path / "config.yaml").write_bytes(b"config")
    manifest = tmp_path / "SHA256SUMS.txt"

    write_manifest(tmp_path, manifest)

    assert validate_manifest(tmp_path, manifest) == []
    assert len(manifest.read_text(encoding="ascii").splitlines()) == 2


def test_manifest_detects_unlisted_files(tmp_path: Path) -> None:
    payload = tmp_path / "payload.bin"
    payload.write_bytes(b"original")
    manifest = tmp_path / "SHA256SUMS.txt"
    write_manifest(tmp_path, manifest)
    (tmp_path / "unexpected.dll").write_bytes(b"untrusted")

    assert validate_manifest(tmp_path, manifest) == ["unexpected.dll: unlisted"]
