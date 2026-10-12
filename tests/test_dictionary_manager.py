from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.dictionary_manager import DictionaryManager, DictionaryPackage
import pytest


def test_import_records_hash_and_license(tmp_path):
    source = tmp_path / "food.yaml"
    source.write_text("terms: []", encoding="utf-8")
    manager = DictionaryManager(tmp_path / "installed", [DictionaryPackage("food", "食材", "builtin://food", "CC0", "allowed")])
    target = manager.import_file(source, "food", "CC0")
    assert target.exists()
    assert (target.parent / "food.sha256").exists()
    assert (target.parent / "food.license.txt").read_text(encoding="utf-8") == "CC0"


def test_https_only_download(tmp_path):
    manager = DictionaryManager(tmp_path)
    package = DictionaryPackage("x", "x", "http://example.com/x", "unknown", "verify")
    try:
        manager.download(package)
    except ValueError as exc:
        assert "HTTPS" in str(exc)


def test_all_packages_includes_existing_resource_and_user_files(tmp_path):
    resources = tmp_path / "resources"
    resources.mkdir()
    (resources / "ai_terms.yaml").write_text("terms: []", encoding="utf-8")
    user = tmp_path / "user"
    user.mkdir()
    (user / "personal_terms.yaml").write_text("terms: []", encoding="utf-8")
    manager = DictionaryManager(user, source_dirs=[resources])
    ids = {item.id for item in manager.all_packages()}
    assert {"ai_terms", "personal_terms"} <= ids


def test_download_url_installs_valid_yaml_pack(tmp_path, monkeypatch):
    payload = b"terms:\n  - canonical: TestAI\n    aliases: [test ai]\n"

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _limit):
            return payload

    monkeypatch.setattr("app.dictionary_manager.urllib.request.urlopen", lambda *_args, **_kwargs: Response())
    manager = DictionaryManager(tmp_path)

    target = manager.download_url("https://example.com/ai_terms.yaml", "custom_ai")

    assert target.read_bytes() == payload
    assert (tmp_path / "custom_ai.sha256").is_file()
    assert (tmp_path / "custom_ai.license.txt").is_file()


def test_download_url_rejects_non_https(tmp_path):
    manager = DictionaryManager(tmp_path)

    try:
        manager.download_url("http://example.com/terms.yaml", "unsafe")
    except ValueError as exc:
        assert "HTTPS" in str(exc)
    else:
        raise AssertionError("non-HTTPS dictionary URL was accepted")


def test_installed_includes_yml_files(tmp_path):
    (tmp_path / "custom.yml").write_text("terms: []", encoding="utf-8")

    assert DictionaryManager(tmp_path).installed() == [tmp_path / "custom.yml"]


def test_import_rejects_invalid_dictionary_structure(tmp_path):
    source = tmp_path / "invalid.yaml"
    source.write_text("name: not-a-dictionary", encoding="utf-8")

    with pytest.raises(ValueError, match="terms"):
        DictionaryManager(tmp_path / "installed").import_file(source, "invalid", "unknown")


def test_import_rejects_unsafe_package_id(tmp_path):
    source = tmp_path / "valid.yaml"
    source.write_text("terms: []", encoding="utf-8")

    with pytest.raises(ValueError, match="名称"):
        DictionaryManager(tmp_path / "installed").import_file(source, "../escape", "unknown")


def test_import_replaces_same_package_with_different_extension(tmp_path):
    installed = tmp_path / "installed"
    installed.mkdir()
    (installed / "custom.yaml").write_text("terms: []", encoding="utf-8")
    source = tmp_path / "custom.json"
    source.write_text('{"terms": []}', encoding="utf-8")

    target = DictionaryManager(installed).import_file(source, "custom", "test")

    assert target == installed / "custom.json"
    assert not (installed / "custom.yaml").exists()
