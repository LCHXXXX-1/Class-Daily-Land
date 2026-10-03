import sys

ERROR_ALREADY_EXISTS = 183
LOCK_NAME = "ClassDailyLand_SingleInstance_Mutex"


def acquire_single_instance_lock(name=LOCK_NAME):
    if sys.platform != 'win32':
        return True

    import ctypes
    kernel32 = ctypes.windll.kernel32

    kernel32.SetLastError(0)
    handle = kernel32.CreateMutexW(None, False, name)
    last_error = kernel32.GetLastError()

    if not handle:
        raise ctypes.WinError(last_error or 1)

    if last_error == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return None
    return handle