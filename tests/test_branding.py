from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.branding import (  # noqa: E402
    APP_VERSION,
    BRAND_NAME,
    OFFICIAL_ACCOUNT_NAME,
    attribution_text,
    official_download_text,
)
from app.config import load_config  # noqa: E402


def test_brand_identity_is_fixed() -> None:
    assert BRAND_NAME == "RanLiAiJAY"
    assert APP_VERSION == "2.0"
    assert attribution_text() == "燃砺AiJAY 提供技术支持"


def test_official_download_points_to_wechat_account() -> None:
    assert OFFICIAL_ACCOUNT_NAME == "燃砺Ai百宝库"
    assert "燃砺Ai百宝库" in official_download_text()


def test_startup_sound_is_enabled_by_default(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "missing-user-config.yaml")
    assert cfg["branding"]["startup_sound"] is True
    assert cfg["branding"]["attribution"] == "燃砺AiJAY 提供技术支持"


def test_rights_notice_names_third_party_license_boundary() -> None:
    text = official_download_text()
    assert "借助 AI 工具研发" in text
    assert "第三方开源组件" in text
    assert "商用权利" in text
