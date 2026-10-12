from pathlib import Path

import pytest

from tools.release_version_info import main, normalize_version, render_version_info


@pytest.mark.parametrize(
    ("release", "expected"),
    [
        ("2.1", (2, 1, 0, 0)),
        ("2.1.7", (2, 1, 7, 0)),
    ],
)
def test_release_version_is_normalized_for_windows(
    release: str, expected: tuple[int, int, int, int]
) -> None:
    assert normalize_version(release) == expected


@pytest.mark.parametrize("release", ["2", "2.1.3.4", "2.x", "2.70000"])
def test_invalid_release_version_is_rejected(release: str) -> None:
    with pytest.raises(ValueError, match="Invalid release version"):
        normalize_version(release)


def test_version_resource_uses_requested_release_version() -> None:
    template = (
        Path(__file__).parents[1] / "resources" / "version_info.txt"
    ).read_text(encoding="utf-8")

    rendered = render_version_info(template, "2.1.7")

    assert "filevers=(2, 1, 7, 0)" in rendered
    assert "prodvers=(2, 1, 7, 0)" in rendered
    assert "StringStruct('FileVersion', '2.1.7.0')" in rendered
    assert "StringStruct('ProductVersion', '2.1.7.0')" in rendered
    assert "2.0.0.0" not in rendered


def test_incomplete_version_template_is_rejected() -> None:
    with pytest.raises(ValueError, match="Version resource field is missing"):
        render_version_info("filevers=(2, 0, 0, 0)", "2.1")


def test_version_resource_cli_writes_rendered_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = Path(__file__).parents[1] / "resources" / "version_info.txt"
    output = tmp_path / "version_info.txt"
    monkeypatch.setattr(
        "sys.argv",
        ["release_version_info.py", str(source), str(output), "3.4"],
    )

    main()

    assert "StringStruct('ProductVersion', '3.4.0.0')" in output.read_text(
        encoding="utf-8"
    )
