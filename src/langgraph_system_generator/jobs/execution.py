"""Supervise generation/upload in a killable process, never a detached thread."""

import asyncio
import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .models import ArtifactRef, DurableJob, JobError, LogLevel


@dataclass(frozen=True)
class ExecutionLimits:
    generation_seconds: int = 240
    publication_margin: int = 45
    attempt_seconds: int = 300
    http_timeout: int = 330
    dispatch_deadline: int = 360

    def __post_init__(self) -> None:
        if (
            any(type(v) is not int for v in vars(self).values())
            or not 1 <= self.generation_seconds <= 240
            or not 1 <= self.publication_margin <= 60
            or self.generation_seconds + self.publication_margin > self.attempt_seconds
            or not self.attempt_seconds
            < self.http_timeout
            < self.dispatch_deadline
            <= 1800
        ):
            raise JobError("execution_configuration_invalid", 503)


def trusted_directory(path: Path) -> Path:
    path = path.absolute()
    if any(
        p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())
        for p in (path, *path.parents)
    ):
        raise JobError("attempt_directory_invalid", 503)
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve(strict=True)


async def kill_and_reap(process: asyncio.subprocess.Process) -> None:
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
    # Do not release capacity until the OS confirms termination. No provider
    # request cancellation or remote-side-effect rollback is implied by this.
    await process.wait()


class SubprocessAttempt:
    def __init__(
        self,
        limits: ExecutionLimits | None = None,
        *,
        command: tuple[str, ...] | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self.limits = limits or ExecutionLimits()
        self.command = command or (
            sys.executable,
            "-m",
            "langgraph_system_generator.jobs.attempt_process",
        )
        self.last_process: asyncio.subprocess.Process | None = None
        self.clock = clock

    async def run(
        self,
        job: DurableJob | None,
        directory: Path,
        progress: Callable[[int | tuple[LogLevel, str]], None],
    ) -> ArtifactRef:
        process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            limit=8192,
        )
        self.last_process = process
        assert process.stdin is not None and process.stdout is not None
        start = time.monotonic()
        overall_end = start + self.limits.attempt_seconds
        if job is not None:
            overall_end = min(
                overall_end, start + max(0, job.deadline_at - self.clock())
            )
        deadline = start + self.limits.generation_seconds
        publishing = False
        receipt = None
        try:
            process.stdin.write(
                (
                    json.dumps(
                        {
                            "job": job.model_dump(mode="json") if job else None,
                            "directory": str(directory),
                        }
                    )
                    + "\n"
                ).encode()
            )
            await asyncio.wait_for(
                process.stdin.drain(), self.limits.generation_seconds
            )
            process.stdin.close()
            while True:
                remaining = min(deadline, overall_end) - time.monotonic()
                if remaining <= 0:
                    raise JobError("attempt_deadline", 503)
                try:
                    line = await asyncio.wait_for(process.stdout.readline(), remaining)
                except asyncio.TimeoutError:
                    raise JobError("attempt_deadline", 503) from None
                if not line:
                    break
                if len(line) > 4096:
                    raise JobError("attempt_protocol_invalid", 503)
                event = json.loads(line)
                if event.get("kind") == "publishing" and not publishing:
                    publishing = True
                    deadline = min(
                        overall_end, time.monotonic() + self.limits.publication_margin
                    )
                elif (
                    event.get("kind") == "progress" and type(event.get("value")) is int
                ):
                    progress(max(0, min(99, event["value"])))
                elif event.get("kind") == "log":
                    if (
                        event.get("level") not in {"info", "warning", "error"}
                        or not isinstance(event.get("message"), str)
                        or len(event["message"]) > 512
                    ):
                        raise JobError("attempt_protocol_invalid", 503)
                    progress((event["level"], event["message"]))
                elif event.get("kind") == "result":
                    receipt = ArtifactRef.model_validate(event["ref"])
                elif event.get("kind") == "error":
                    raise JobError(
                        (
                            "attempt_permanent_failure"
                            if event.get("permanent")
                            else "attempt_infrastructure_failure"
                        ),
                        422 if event.get("permanent") else 503,
                    )
            remaining = min(deadline, overall_end) - time.monotonic()
            try:
                await asyncio.wait_for(process.wait(), max(0.001, remaining))
            except asyncio.TimeoutError:
                raise JobError("attempt_deadline", 503) from None
            if process.returncode != 0 or receipt is None or not publishing:
                raise JobError("attempt_infrastructure_failure", 503)
            return receipt
        except (ValueError, KeyError, TypeError):
            raise JobError("attempt_protocol_invalid", 503) from None
        finally:
            # Even a cancellation-suppressing generator or blocking export dies
            # here; no success/capacity release before reaping the owned child.
            await asyncio.shield(kill_and_reap(process))


async def reconciliation_process() -> dict[str, int]:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "langgraph_system_generator.jobs.attempt_process",
        "--reconcile",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        limit=8192,
    )
    try:
        assert process.stdout is not None
        line = await asyncio.wait_for(process.stdout.readline(), 55)
        await asyncio.wait_for(process.wait(), 5)
        if process.returncode != 0 or len(line) > 4096:
            raise JobError("reconciliation_unavailable", 503)
        result = json.loads(line)
        if not isinstance(result, dict) or any(
            type(v) is not int for v in result.values()
        ):
            raise JobError("reconciliation_unavailable", 503)
        return result
    except (asyncio.TimeoutError, ValueError):
        raise JobError("reconciliation_unavailable", 503) from None
    finally:
        await asyncio.shield(kill_and_reap(process))
