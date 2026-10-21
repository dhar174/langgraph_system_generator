"""Own a subprocess tree even after its immediate parent exits normally."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time


class ProcessScope:
    """A private POSIX session or an unnamed Windows Job Object."""

    def __init__(self):
        self.job = None
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            self.api = ctypes.WinDLL("kernel32", use_last_error=True)
            self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
            self.api.CreateJobObjectW.restype = wintypes.HANDLE
            self.api.AssignProcessToJobObject.argtypes = [
                wintypes.HANDLE,
                wintypes.HANDLE,
            ]
            self.api.AssignProcessToJobObject.restype = wintypes.BOOL
            self.api.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
            self.api.TerminateJobObject.restype = wintypes.BOOL
            self.api.CloseHandle.argtypes = [wintypes.HANDLE]
            self.api.CloseHandle.restype = wintypes.BOOL
            self.job = self.api.CreateJobObjectW(None, None)
            if not self.job:
                raise ctypes.WinError(ctypes.get_last_error())

    def start(self, command, **kwargs):
        if os.name != "nt":
            return subprocess.Popen(command, start_new_session=True, **kwargs)
        import ctypes

        # Gate command execution until the launcher belongs to our job. Children
        # inherit membership, including children surviving a normal launcher exit.
        launcher = (
            "import subprocess,sys; "
            "assert sys.stdin.buffer.read(1)==b'1'; "
            "raise SystemExit(subprocess.call(sys.argv[1:],stdin=subprocess.DEVNULL))"
        )
        process = subprocess.Popen(
            [sys.executable, "-c", launcher, *command],
            stdin=subprocess.PIPE,
            **kwargs,
        )
        try:
            if not self.api.AssignProcessToJobObject(self.job, int(process._handle)):
                raise ctypes.WinError(ctypes.get_last_error())
            process.stdin.write(b"1")
            process.stdin.close()
            return process
        except BaseException:
            process.kill()
            process.wait(timeout=5)
            raise

    def stop(self, process):
        try:
            if os.name == "nt":
                import ctypes

                if not self.api.TerminateJobObject(self.job, 1):
                    raise ctypes.WinError(ctypes.get_last_error())
            else:
                # The session/group was created by start(), never discovered by
                # looking up a reaped parent PID. Do not adopt external groups.
                for sig in (signal.SIGTERM, signal.SIGKILL):
                    try:
                        os.killpg(process.pid, sig)
                    except ProcessLookupError:
                        break
                    if sig == signal.SIGTERM:
                        time.sleep(0.1)
            process.wait(timeout=5)
        finally:
            self.close()

    def close(self):
        if self.job is not None:
            self.api.CloseHandle(self.job)
            self.job = None
