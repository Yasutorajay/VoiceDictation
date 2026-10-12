from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_official_dictionary_metadata_and_notices_exist() -> None:
    dictionary_root = ROOT / "resources" / "dictionaries"
    packages = [dictionary_root / "wordnet_3_0.json", *dictionary_root.glob("thuocl_*.json")]
    assert len(packages) == 12
    for package in packages:
        payload = json.loads(package.read_text(encoding="utf-8"))
        assert payload["entries"]
        assert payload["metadata"]["source"].startswith("https://")
        assert package.with_suffix(".sha256").is_file()
    assert (dictionary_root / "licenses" / "WORDNET_LICENSE.txt").is_file()
    assert (dictionary_root / "licenses" / "THUOCL_LICENSE.txt").is_file()


def test_external_dictionary_resources_are_versioned_and_licensed() -> None:
    dictionary_root = ROOT / "resources" / "dictionaries"
    expected = {
        "rime_ice_english.json": "GPL-3.0-only",
        "jargons_dev_terms.json": "GPL-2.0-only",
        "deepseek_v4_tokens.json": "MIT",
    }
    for name, license_name in expected.items():
        package = dictionary_root / name
        payload = json.loads(package.read_text(encoding="utf-8"))
        assert payload["entries"]
        assert payload["metadata"]["source"].startswith("https://github.com/")
        assert len(payload["metadata"]["commit"]) == 40
        assert license_name in payload["metadata"]["license"]
        assert package.with_suffix(".sha256").is_file()
        assert package.with_suffix(".license.txt").is_file()


def test_unlicensed_or_ambiguous_sources_are_links_only() -> None:
    import yaml

    catalog = yaml.safe_load(
        (ROOT / "resources" / "dictionaries" / "external_sources.yaml").read_text(encoding="utf-8")
    )
    by_id = {item["id"]: item for item in catalog["sources"]}
    assert by_id["meta_dictionary"]["status"] == "link_only"
    assert by_id["chinese_internet_jargon"]["status"] == "link_only"
