"""Configure existing ProcessScope's Windows job; POSIX limits live in child."""

import os


def configure_limits(scope, memory_mb, cpu_seconds):
    if os.name != "nt":
        return {"memory": "per-process RLIMIT_AS", "cpu": "per-process RLIMIT_CPU"}
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [
            ("process_time", ctypes.c_int64),
            ("job_time", ctypes.c_int64),
            ("flags", wintypes.DWORD),
            ("min_ws", ctypes.c_size_t),
            ("max_ws", ctypes.c_size_t),
            ("active", wintypes.DWORD),
            ("affinity", ctypes.c_size_t),
            ("priority", wintypes.DWORD),
            ("scheduling", wintypes.DWORD),
        ]

    class IO(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_uint64)
            for name in [
                "read_ops",
                "write_ops",
                "other_ops",
                "read_bytes",
                "write_bytes",
                "other_bytes",
            ]
        ]

    class Extended(ctypes.Structure):
        _fields_ = [
            ("basic", Basic),
            ("io", IO),
            ("process_memory", ctypes.c_size_t),
            ("job_memory", ctypes.c_size_t),
            ("peak_process", ctypes.c_size_t),
            ("peak_job", ctypes.c_size_t),
        ]

    info = Extended()
    info.basic.flags = (
        0x00000200 | 0x00000004 | 0x00002000
    )  # job memory, CPU time, kill on close
    info.basic.job_time = cpu_seconds * 10_000_000
    info.job_memory = memory_mb * 1024**2
    scope.api.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    scope.api.SetInformationJobObject.restype = wintypes.BOOL
    if not scope.api.SetInformationJobObject(
        scope.job, 9, ctypes.byref(info), ctypes.sizeof(info)
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return {
        "memory": "aggregate Windows Job Object committed memory",
        "cpu": "aggregate Windows Job Object user CPU time",
    }
