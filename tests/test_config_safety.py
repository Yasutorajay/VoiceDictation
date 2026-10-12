from pathlib import Path


def test_live_preview_serialization_is_documented():
    text = (Path(__file__).parents[1] / "config.default.yaml").read_text(encoding="utf-8")
    assert "live_preview:\n  # Preview and final decoding share one locked recognizer" in text
    import yaml
    assert yaml.safe_load(text)["live_preview"]["enabled"] is True
