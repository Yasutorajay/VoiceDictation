import ctypes
import os

MUTEX_NAME = r"Local\VoiceDictationSingleton"
SYNCHRONIZE = 0x00100000
ERROR_FILE_NOT_FOUND = 2
ERROR_ALREADY_EXISTS = 183
_startup_handle = None


def another_instance_running() -> bool:
    global _startup_handle
    if os.name != "nt":
        return False
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenMutexW.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.OpenMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_bool
    handle = kernel.OpenMutexW(SYNCHRONIZE, False, MUTEX_NAME)
    if handle:
        kernel.CloseHandle(handle)
        return True
    error = ctypes.get_last_error()
    if error != ERROR_FILE_NOT_FOUND:
        raise ctypes.WinError(error)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.SetLastError(0)
    handle = kernel.CreateMutexW(None, False, MUTEX_NAME + ".StartupGuard")
    error = ctypes.get_last_error()
    if not handle:
        raise ctypes.WinError(error)
    if error == ERROR_ALREADY_EXISTS:
        kernel.CloseHandle(handle)
        return True
    _startup_handle = handle
    return False
