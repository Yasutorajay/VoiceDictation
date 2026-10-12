from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


def _read_terms(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.is_file():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = data.get("terms", []) if isinstance(data, dict) else []
    if not isinstance(entries, list):
        raise ValueError(f"Terminology terms must be a list: {path}")
    return [entry for entry in entries if isinstance(entry, dict)]


def load_terminology(
    builtin_path: Path | None,
    user_path: Path | None = None,
    installed_dir: Path | None = None,
) -> dict[str, list[str]]:
    alias_owner: dict[str, tuple[str, str]] = {}
    canonical_order: list[str] = []
    installed_paths = []
    if installed_dir is not None and installed_dir.is_dir():
        installed_paths = sorted(
            [
                *installed_dir.glob("*.yaml"),
                *installed_dir.glob("*.yml"),
                *installed_dir.glob("*.json"),
            ]
        )
    entries = [*_read_terms(builtin_path)]
    for path in installed_paths:
        entries.extend(_read_terms(path))
    entries.extend(_read_terms(user_path))
    for entry in entries:
        canonical = str(entry.get("canonical", "")).strip()
        if not canonical:
            continue
        if canonical not in canonical_order:
            canonical_order.append(canonical)
        aliases = entry.get("aliases", [])
        if not isinstance(aliases, list):
            raise ValueError(f"Aliases must be a list for term: {canonical}")
        for raw_alias in [canonical, *aliases]:
            alias = str(raw_alias).strip()
            if alias:
                alias_owner[alias.casefold()] = (alias, canonical)

    result = {canonical: [] for canonical in canonical_order}
    for alias, canonical in alias_owner.values():
        result.setdefault(canonical, []).append(alias)
    return {canonical: aliases for canonical, aliases in result.items() if aliases}


class TerminologyCorrector:
    def __init__(self, terms: dict[str, list[str]]) -> None:
        replacements: list[tuple[str, str]] = []
        for canonical, aliases in terms.items():
            for alias in aliases:
                normalized = str(alias).strip()
                if normalized:
                    replacements.append((normalized, canonical))
        replacements.sort(key=lambda item: len(item[0]), reverse=True)
        self._canonical_by_alias = {
            alias.casefold(): canonical for alias, canonical in replacements
        }
        alternatives = []
        for alias, _canonical in replacements:
            escaped = re.escape(alias)
            left = (
                r"(?<![A-Za-z0-9_])"
                if alias[0].isascii() and alias[0].isalnum()
                else ""
            )
            right = (
                r"(?![A-Za-z0-9_])"
                if alias[-1].isascii() and alias[-1].isalnum()
                else ""
            )
            alternatives.append(left + escaped + right)
        self._pattern = re.compile("|".join(alternatives), re.IGNORECASE) if alternatives else None

    def apply(self, text: str) -> str:
        if self._pattern is None:
            return text
        return self._pattern.sub(
            lambda match: self._canonical_by_alias[match.group(0).casefold()], text
        )
