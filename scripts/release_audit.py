from __future__ import annotations

import hashlib
import re
from pathlib import Path
from zipfile import ZipFile

import yaml

ALLOWED_TOP_LEVEL = frozenset({
    "VoiceDictation.exe", "config.yaml", "_internal", "data", "resources",
    "ThirdPartyLicenses", "LICENSE_OR_TERMS_ZH.txt", "README.md",
    "README_PORTABLE.txt", "USER_GUIDE_ZH.md", "SHA256SUMS.txt",
    "start_voice_dictation.bat", "verify_package.bat", "verify_package.ps1",
})
ASSET_ALLOWLIST = Path(__file__).with_name("release_asset_allowlist.txt")
TEXT_SUFFIXES = frozenset({".yaml", ".yml", ".json", ".md", ".txt", ".toml", ".bat", ".ps1", ".ini", ".cfg"})
FORBIDDEN_SUFFIXES = frozenset({".py", ".pyc", ".log", ".pem", ".key", ".pfx", ".p12", ".db", ".sqlite", ".sqlite3", ".flac", ".ogg", ".zip", ".7z", ".rar"})
FORBIDDEN_NAMES = frozenset({".env", "credentials.json", "secrets.json", "id_rsa", "id_ed25519"})
PRIVATE_PATH = re.compile(r"(?i)\b[A-Z]:[\\/](?:Users|Documents|AI-Tools)[\\/]")
CREDENTIAL = re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*['\"]?[^\s'\"]{12,}")


def _audit_config(path: Path) -> list[str]:
    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        return [f"config.yaml: unreadable or invalid: {exc}"]
    paths = config.get("paths") if isinstance(config, dict) else None
    if not isinstance(paths, dict) or paths.get("data_dir") != "data":
        return ["config.yaml: data_dir must be the clean relative 'data' path"]
    return []


def _allowed_assets() -> frozenset[str]:
    return frozenset(line.strip() for line in ASSET_ALLOWLIST.read_text(encoding="utf-8-sig").splitlines() if line.strip())


def audit_portable_tree(root: Path) -> list[str]:
    errors: list[str] = []
    if not root.is_dir():
        return [f"Missing package directory: {root}"]
    allowed_assets = _allowed_assets()
    for entry in root.iterdir():
        if entry.name not in ALLOWED_TOP_LEVEL:
            errors.append(f"Unexpected top-level entry: {entry.name}")
    if not (root / "VoiceDictation.exe").is_file():
        errors.append("Missing VoiceDictation.exe")
    config = root / "config.yaml"
    errors.extend(_audit_config(config) if config.is_file() else ["Missing config.yaml"])
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        lowered = relative.lower()
        if path.is_symlink():
            errors.append(f"Linked path forbidden: {relative}")
            continue
        if path.is_dir():
            if lowered in {"data/logs", "data/recordings", "data/captures"}:
                errors.append(f"Private data directory forbidden: {relative}")
            continue
        approved_name = ("resources/licenses/" + relative.removeprefix("ThirdPartyLicenses/licenses/")) if relative.startswith("ThirdPartyLicenses/licenses/") else relative
        if relative.startswith("data/") and not relative.startswith("data/models/"):
            errors.append(f"Unexpected data file: {relative}")
        if (relative.startswith(("resources/", "data/models/", "ThirdPartyLicenses/licenses/")) and approved_name not in allowed_assets):
            errors.append(f"Unapproved resource: {relative}")
        if ((path.suffix.lower() in FORBIDDEN_SUFFIXES and relative != "_internal/base_library.zip") or path.name.lower() in FORBIDDEN_NAMES):
            errors.append(f"Forbidden file: {relative}")
        if path.suffix.lower() in {".wav", ".mp3"} and lowered != "resources/startup.wav":
            errors.append(f"Audio file forbidden: {relative}")
        if any(part.lower() in {".git", ".github", ".vscode", "__pycache__", "recovery_artifacts"} for part in path.parts):
            errors.append(f"Development file forbidden: {relative}")
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if path.stat().st_size > 10_000_000:
            errors.append(f"Oversized text file requires review: {relative}")
            continue
        try:
            contents = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            errors.append(f"Unreadable text file: {relative}")
            continue
        if PRIVATE_PATH.search(contents) or "-----BEGIN PRIVATE KEY-----" in contents:
            errors.append(f"Private path or key in: {relative}")
        if CREDENTIAL.search(contents):
            errors.append(f"Credential-like value in: {relative}")
    return errors


def audit_zip_against_tree(archive: Path, root: Path) -> list[str]:
    errors: list[str] = []
    expected = {path.relative_to(root).as_posix(): path for path in root.rglob("*") if path.is_file()}
    with ZipFile(archive) as zipped:
        members = [entry for entry in zipped.infolist() if not entry.is_dir()]
        names = [entry.filename for entry in members]
        prefix = root.name + "/"
        relative_names = [name[len(prefix):] for name in names if name.startswith(prefix)]
        if len(relative_names) != len(names) or len(set(relative_names)) != len(names):
            errors.append("ZIP contains unexpected or duplicate members")
        errors.extend(f"ZIP missing file: {name}" for name in sorted(set(expected) - set(relative_names)))
        errors.extend(f"ZIP extra file: {name}" for name in sorted(set(relative_names) - set(expected)))
        for member in members:
            if not member.filename.startswith(prefix):
                continue
            relative = member.filename[len(prefix):]
            source = expected.get(relative)
            if source is None:
                continue
            with source.open("rb") as file_handle, zipped.open(member) as zip_handle:
                source_hash = hashlib.file_digest(file_handle, "sha256").digest()
                zip_hash = hashlib.file_digest(zip_handle, "sha256").digest()
            if source_hash != zip_hash:
                errors.append(f"ZIP content differs: {relative}")
    return errors
