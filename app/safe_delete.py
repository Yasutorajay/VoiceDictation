from __future__ import annotations

import errno
import os
from pathlib import Path


WINDOWS_DELETE_ACCESS = 0x00010000
WINDOWS_READ_ATTRIBUTES = 0x00000080
WINDOWS_SHARE_READ_WRITE = 0x00000003
WINDOWS_OPEN_EXISTING = 3
WINDOWS_OPEN_REPARSE_POINT = 0x00200000
WINDOWS_FILE_DISPOSITION_INFO = 4
WINDOWS_MISSING_ERRORS = frozenset({2, 3})
WINDOWS_PATH_BUFFER_SIZE = 32768


def _normalized_path(path: Path | str) -> str:
    value = str(path)
    if value.startswith("\\\\?\\UNC\\"):
        value = "\\\\" + value[8:]
    elif value.startswith("\\\\?\\"):
        value = value[4:]
    return os.path.normcase(os.path.abspath(value))


def _windows_api() -> tuple[object, object, object, object]:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    get_final_path = kernel32.GetFinalPathNameByHandleW
    get_final_path.argtypes = (
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    )
    get_final_path.restype = wintypes.DWORD
    set_file_info = kernel32.SetFileInformationByHandle
    set_file_info.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    )
    set_file_info.restype = wintypes.BOOL
    return create_file, close_handle, get_final_path, set_file_info


def _windows_final_path(handle: object, get_final_path: object) -> str:
    import ctypes

    buffer = ctypes.create_unicode_buffer(WINDOWS_PATH_BUFFER_SIZE)
    length = get_final_path(handle, buffer, WINDOWS_PATH_BUFFER_SIZE, 0)
    if length == 0 or length >= WINDOWS_PATH_BUFFER_SIZE:
        raise ctypes.WinError(ctypes.get_last_error())
    return buffer.value


def _mark_windows_handle_for_deletion(handle: object, set_file_info: object) -> None:
    import ctypes
    from ctypes import wintypes

    class FileDispositionInfo(ctypes.Structure):
        _fields_ = (("delete_file", wintypes.BOOL),)

    disposition = FileDispositionInfo(True)
    if not set_file_info(
        handle,
        WINDOWS_FILE_DISPOSITION_INFO,
        ctypes.byref(disposition),
        ctypes.sizeof(disposition),
    ):
        raise ctypes.WinError(ctypes.get_last_error())


def _delete_file_on_windows(path: Path, expected: Path) -> bool:
    import ctypes
    from ctypes import wintypes

    create_file, close_handle, get_final_path, set_file_info = _windows_api()
    handle = create_file(
        str(path),
        WINDOWS_DELETE_ACCESS | WINDOWS_READ_ATTRIBUTES,
        WINDOWS_SHARE_READ_WRITE,
        None,
        WINDOWS_OPEN_EXISTING,
        WINDOWS_OPEN_REPARSE_POINT,
        None,
    )
    if handle == wintypes.HANDLE(-1).value:
        error = ctypes.get_last_error()
        if error in WINDOWS_MISSING_ERRORS:
            return False
        raise ctypes.WinError(error)
    try:
        final_path = _windows_final_path(handle, get_final_path)
        if _normalized_path(final_path) != _normalized_path(expected):
            raise ValueError(f"Unsafe private file path: {final_path}")
        _mark_windows_handle_for_deletion(handle, set_file_info)
        return True
    finally:
        close_handle(handle)


def _delete_file_on_posix(path: Path, expected: Path) -> bool:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        directory_handle = os.open(path.parent, flags)
    except FileNotFoundError:
        return False
    try:
        descriptor_path = Path(f"/proc/self/fd/{directory_handle}")
        directory_path = Path(os.path.realpath(descriptor_path))
        if _normalized_path(directory_path / path.name) != _normalized_path(expected):
            raise ValueError(f"Unsafe private file path: {directory_path / path.name}")
        try:
            os.unlink(path.name, dir_fd=directory_handle)
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                return False
            raise
        return True
    finally:
        os.close(directory_handle)


def delete_file_by_verified_handle(path: Path, expected: Path) -> bool:
    if os.name == "nt":
        return _delete_file_on_windows(path, expected)
    return _delete_file_on_posix(path, expected)
