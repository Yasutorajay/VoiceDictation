from pathlib import Path

from scripts.release_audit import audit_portable_tree


def make_package(root: Path) -> Path:
    root.mkdir()
    (root / "VoiceDictation.exe").write_bytes(b"binary")
    (root / "config.yaml").write_text("paths:\n  data_dir: data\n", encoding="utf-8")
    (root / "data" / "models").mkdir(parents=True)
    (root / "resources").mkdir()
    return root


def test_release_audit_accepts_clean_package(tmp_path: Path) -> None:
    package = make_package(tmp_path / "package")
    assert audit_portable_tree(package) == []


def test_release_audit_rejects_development_and_personal_files(tmp_path: Path) -> None:
    package = make_package(tmp_path / "package")
    (package / "main.py").write_text("private", encoding="utf-8")
    (package / "data" / "logs").mkdir()
    (package / "data" / "logs" / "app.log").write_text("private", encoding="utf-8")
    errors = audit_portable_tree(package)
    assert any("main.py" in error for error in errors)
    assert any("data/logs" in error for error in errors)


def test_release_audit_rejects_private_config_and_credentials(tmp_path: Path) -> None:
    package = make_package(tmp_path / "package")
    (package / "config.yaml").write_text("paths:\n  data_dir: C:\\Users\\Alice\\secret\n", encoding="utf-8")
    (package / "resources" / "secret.txt").write_text("api_key = sk-test-example-1234567890", encoding="utf-8")
    errors = audit_portable_tree(package)
    assert any("config.yaml" in error for error in errors)
    assert any("secret.txt" in error for error in errors)


def test_release_audit_rejects_unexpected_top_level_files(tmp_path: Path) -> None:
    package = make_package(tmp_path / "package")
    (package / "SOURCE_HANDOFF.md").write_text("internal", encoding="utf-8")
    assert any("SOURCE_HANDOFF.md" in error for error in audit_portable_tree(package))


def test_release_audit_rejects_nested_private_data(tmp_path: Path) -> None:
    package = make_package(tmp_path / "package")
    (package / "resources" / "credentials.env").write_text("private", encoding="utf-8")
    (package / "resources" / "customer.sqlite").write_bytes(b"private")
    errors = audit_portable_tree(package)
    assert any("credentials.env" in error for error in errors)
    assert any("customer.sqlite" in error for error in errors)


def test_zip_audit_rejects_modified_content(tmp_path: Path) -> None:
    from zipfile import ZIP_DEFLATED, ZipFile

    from scripts.release_audit import audit_zip_against_tree

    package = make_package(tmp_path / "package")
    archive = tmp_path / "package.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as zip_file:
        zip_file.writestr("package/VoiceDictation.exe", b"tampered")
        zip_file.writestr("package/config.yaml", (package / "config.yaml").read_bytes())
    assert any("VoiceDictation.exe" in error for error in audit_zip_against_tree(archive, package))


def test_release_audit_rejects_unknown_data_file(tmp_path: Path) -> None:
    package = make_package(tmp_path / "package")
    (package / "data" / "private.bin").write_bytes(b"private")
    assert any("data/private.bin" in error for error in audit_portable_tree(package))
