"""Windows child-process ownership and launcher lifetime monitoring."""
from contextlib import contextmanager
import os
import threading


def _windows_api():
    import ctypes
    from ctypes import wintypes
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    signatures = {
        'CreateJobObjectW': ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
        'SetInformationJobObject': ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
        'AssignProcessToJobObject': ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
        'CloseHandle': ([wintypes.HANDLE], wintypes.BOOL),
        'OpenProcess': ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        'WaitForSingleObject': ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(api, name)
        function.argtypes, function.restype = arguments, result
    return api


class ChildProcessJob:
    """Kill managed Windows children even when the owner is forcibly stopped."""

    def __init__(self):
        self.handle = None
        if os.name != 'nt':
            return
        import ctypes
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64),
                        ('PerJobUserTimeLimit', ctypes.c_int64), ('LimitFlags', wintypes.DWORD),
                        ('MinimumWorkingSetSize', ctypes.c_size_t), ('MaximumWorkingSetSize', ctypes.c_size_t),
                        ('ActiveProcessLimit', wintypes.DWORD), ('Affinity', ctypes.c_size_t),
                        ('PriorityClass', wintypes.DWORD), ('SchedulingClass', wintypes.DWORD)]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [('BasicLimitInformation', BasicLimits), ('IoInfo', ctypes.c_uint64 * 6),
                        ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                        ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]

        self.api = _windows_api()
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def add(self, process):
        if self.handle and not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            import ctypes
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


@contextmanager
def watch_parent():
    """Stop the actual interpreter if an IDE kills its Windows venv launcher."""
    if os.name != 'nt':
        yield
        return
    api = _windows_api()
    handle = api.OpenProcess(0x00100000, False, os.getppid())  # SYNCHRONIZE
    if not handle:
        # The launcher may already have exited before Python finished starting.
        raise RuntimeError('Не удалось подключиться к процессу, запустившему приложение.')
    finished = threading.Event()

    def monitor():
        import _thread
        try:
            while not finished.is_set():
                if api.WaitForSingleObject(handle, 200) == 0:
                    if not finished.is_set():
                        _thread.interrupt_main()
                    return
        finally:
            api.CloseHandle(handle)

    worker = threading.Thread(target=monitor, name='launcher-monitor', daemon=True)
    worker.start()
    try:
        yield
    finally:
        finished.set()
        worker.join(timeout=1)
