"""Bounded synthetic-only redaction probe; run under a parent subprocess timeout."""

import argparse
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import re
import time


def limit_memory():
    """Cap the disposable interpreter at 512 MiB on Windows and POSIX."""
    maximum = 512 * 1024 * 1024
    if os.name != "nt":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (maximum, maximum))
        return
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ("process_time", ctypes.c_int64),
            ("job_time", ctypes.c_int64),
            ("flags", wintypes.DWORD),
            ("min_working_set", ctypes.c_size_t),
            ("max_working_set", ctypes.c_size_t),
            ("active_processes", wintypes.DWORD),
            ("affinity", ctypes.c_size_t),
            ("priority", wintypes.DWORD),
            ("scheduling", wintypes.DWORD),
        ]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("basic", BasicLimits),
            ("io", ctypes.c_uint64 * 6),
            ("process_memory", ctypes.c_size_t),
            ("job_memory", ctypes.c_size_t),
            ("peak_process_memory", ctypes.c_size_t),
            ("peak_job_memory", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    job = kernel.CreateJobObjectW(None, None)
    limits = ExtendedLimits()
    limits.basic.flags = 0x100
    limits.process_memory = maximum
    if (
        not job
        or not kernel.SetInformationJobObject(
            job, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        )
        or not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess())
    ):
        raise ctypes.WinError(ctypes.get_last_error())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("legacy", "candidate"))
    parser.add_argument(
        "family", choices=("query", "json", "fallback", "tail", "mixed")
    )
    parser.add_argument("size", type=int, choices=range(1, 65537))
    args = parser.parse_args()
    if args.mode == "legacy" and args.family not in {"query", "json", "fallback"}:
        parser.error("legacy mode supports only query, json, and fallback families")
    limit_memory()
    repeated = "key" * args.size
    inputs = {
        "query": "&" + repeated + "! access_token=FAKE_PROBE_SECRET",
        "json": '"' + repeated + '! "client_secret": "FAKE_PROBE_SECRET"',
        "fallback": "https://[invalid/?" + repeated + "!&token=FAKE_PROBE_SECRET",
        "tail": "https://example.test/?token=FAKE_PROBE_SECRET" + "." * args.size,
        "mixed": ('key! "key! bearer! key=FAKE_PROBE_SECRET& ' * args.size),
    }
    text = inputs[args.family]
    started = time.perf_counter()
    if args.mode == "legacy":
        patterns = {
            "query": r"((?:[?&]|\b)[\w\-]*(?:key|token|secret|password|auth|cred|signature)[\w\-]*\s*=\s*)[^&\s,'\"<>]+",
            "json": r'(["\'][\w\-]*(?:key|token|secret|password|auth|cred|signature)[\w\-]*["\']\s*:\s*["\'])[^"\']+',
            "fallback": r"((?:[?&]|\b)[\w\-]*(?:key|token|secret|password|auth|cred|signature)[\w\-]*=)[^&\s]+",
        }
        output = re.sub(patterns[args.family], r"\1[REDACTED]", text, flags=re.I)
    else:
        path = (
            Path(__file__).resolve().parents[2]
            / "src/langgraph_system_generator/utils/credential_redaction.py"
        )
        spec = importlib.util.spec_from_file_location("credential_redaction", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sanitizer = (
            module._sanitize_url_for_logging
            if args.family == "fallback"
            else module._sanitize_text_credentials
        )
        output = sanitizer(text)
        assert "FAKE_PROBE_SECRET" not in output
        assert "[REDACTED]" in output or output == "[invalid URL omitted]"
    print(
        json.dumps(
            {
                "family": args.family,
                "size": args.size,
                "characters": len(text),
                "seconds": time.perf_counter() - started,
            }
        )
    )


if __name__ == "__main__":
    main()
