from __future__ import annotations

import argparse
import re
from pathlib import Path


VERSION_PATTERN = re.compile(r"^\d+\.\d+(?:\.\d+)?$")
MAX_WINDOWS_VERSION_PART = 65535


def normalize_version(release: str) -> tuple[int, int, int, int]:
    if not VERSION_PATTERN.fullmatch(release):
        raise ValueError(f"Invalid release version: {release}")
    parts = tuple(int(part) for part in release.split("."))
    if any(part > MAX_WINDOWS_VERSION_PART for part in parts):
        raise ValueError(f"Invalid release version: {release}")
    return (*parts, *(0 for _ in range(4 - len(parts))))


def _replace_once(text: str, pattern: str, replacement: str) -> str:
    rendered, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise ValueError(f"Version resource field is missing: {pattern}")
    return rendered


def render_version_info(template: str, release: str) -> str:
    parts = normalize_version(release)
    tuple_value = f"({', '.join(str(part) for part in parts)})"
    string_value = ".".join(str(part) for part in parts)
    replacements = (
        (r"(?<=filevers=)\(\d+(?:,\s*\d+){3}\)", tuple_value),
        (r"(?<=prodvers=)\(\d+(?:,\s*\d+){3}\)", tuple_value),
        (
            r"(?<=StringStruct\('FileVersion', ')[^']+(?='\))",
            string_value,
        ),
        (
            r"(?<=StringStruct\('ProductVersion', ')[^']+(?='\))",
            string_value,
        ),
    )
    rendered = template
    for pattern, replacement in replacements:
        rendered = _replace_once(rendered, pattern, replacement)
    return rendered


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("template", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("version")
    args = parser.parse_args()
    template = args.template.read_text(encoding="utf-8")
    args.output.write_text(
        render_version_info(template, args.version),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
