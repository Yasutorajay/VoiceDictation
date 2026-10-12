from __future__ import annotations

import importlib.metadata as metadata
import shutil
from pathlib import Path


PACKAGES = {
    "sherpa-onnx": "Apache-2.0",
    "numpy": "BSD-3-Clause",
    "scipy": "BSD-3-Clause",
    "sounddevice": "MIT",
    "pyperclip": "BSD-3-Clause",
    "keyboard": "MIT",
    "pystray": "LGPL-3.0-or-later",
    "pillow": "HPND/PIL",
    "pyyaml": "MIT",
    "psutil": "BSD/MIT",
    "pypinyin": "MIT",
}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out = root / "resources" / "licenses" / "python-packages"
    out.mkdir(parents=True, exist_ok=True)
    rows = ["VoiceDictation third-party package license inventory", "", "Package | Version | Declared license"]
    for name, declared in PACKAGES.items():
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            rows.append(f"{name} | unavailable in build interpreter | {declared}")
            continue
        rows.append(f"{name} | {dist.version} | {declared}")
        for item in dist.files or ():
            if any(token in str(item).lower() for token in ("license", "notice", "copying")):
                source = Path(dist.locate_file(item))
                if source.is_file():
                    target = out / f"{name}-{source.name}"
                    shutil.copyfile(source, target)
    (out / "INDEX.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
