from pathlib import Path

import pytest

from app.safe_delete import WINDOWS_SHARE_READ_WRITE, delete_file_by_verified_handle


def test_windows_handle_does_not_allow_concurrent_rename() -> None:
    file_share_delete = 0x00000004

    assert WINDOWS_SHARE_READ_WRITE & file_share_delete == 0


def test_verified_handle_deletes_expected_file(tmp_path: Path) -> None:
    target = tmp_path / "logs" / "last_result.txt"
    target.parent.mkdir()
    target.write_text("private", encoding="utf-8")

    assert delete_file_by_verified_handle(target, target)
    assert not target.exists()


def test_verified_handle_refuses_file_outside_expected_path(tmp_path: Path) -> None:
    outside = tmp_path / "outside" / "last_result.txt"
    expected = tmp_path / "data" / "logs" / "last_result.txt"
    outside.parent.mkdir()
    outside.write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsafe private file path"):
        delete_file_by_verified_handle(outside, expected)

    assert outside.read_text(encoding="utf-8") == "keep"


def test_verified_handle_treats_missing_file_as_complete(tmp_path: Path) -> None:
    target = tmp_path / "logs" / "last_result.txt"

    assert not delete_file_by_verified_handle(target, target)
