from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import load_config


def test_escape_ime_is_disabled_by_default(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "missing-user-config.yaml")

    assert cfg["inject"]["escape_ime"] is False
