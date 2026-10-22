"""Private subprocess entry point; no notebook execution or detached work."""

import asyncio
import contextlib
import json
import os
import sys
import time
from pathlib import Path

from .models import DurableJob, JobError


async def generate(payload: dict, send) -> None:
    from langgraph_system_generator.cli import generate_artifacts
    from langgraph_system_generator.utils.credential_redaction import (
        _sanitize_text_credentials,
    )

    from .execution import trusted_directory
    from .gcs_artifacts import GCSArtifactStore
    from .providers import resolve_provider

    job = DurableJob.model_validate(payload["job"])
    root = trusted_directory(Path(os.environ["LNF_WORKER_OUTPUT_ROOT"]))
    directory = trusted_directory(Path(payload["directory"]))
    directory.relative_to(root)
    provider = resolve_provider(job.request)
    last_progress = 0.0
    last_log = 0.0

    def progress(event, percentage=None, message=None):
        nonlocal last_progress, last_log
        now = time.monotonic()
        if isinstance(event, dict) and event.get("event") == "log":
            if now - last_log >= 1:
                last_log = now
                level = event.get("level", event.get("status", "info"))
                send(
                    {
                        "kind": "log",
                        "level": (
                            level if level in {"info", "warning", "error"} else "info"
                        ),
                        "message": _sanitize_text_credentials(
                            str(event.get("message", ""))
                        )[:512],
                    }
                )
            return
        if now - last_progress < 1:
            return
        value = event.get("percentage") if isinstance(event, dict) else percentage
        if type(value) is int:
            last_progress = now
            send({"kind": "progress", "value": max(0, min(99, value))})

    await generate_artifacts(
        job.request.prompt,
        output_dir=directory,
        mode=job.request.mode,
        model=job.request.model,
        agent_type=job.request.architecture,
        custom_endpoint=provider.endpoint,
        endpoint_policy="hosted",
        formats=list(job.request.formats) if job.request.formats is not None else None,
        temperature=job.request.temperature,
        max_tokens=job.request.max_tokens,
        requirements_messages=[
            {"role": turn.role, "content": turn.content}
            for turn in job.request.messages
        ]
        or None,
        progress_callback=progress,
    )
    # Quality is in the manifest. A valid diagnostic result is authoritative
    # completion, not a reason to retry a whole generation. Structural artifact
    # validation, provider authorization and infrastructure policy stay intact.
    send({"kind": "publishing"})
    # Reauthorize after generation too; removed registrations cannot publish a
    # policy-bypassing result after a long provider call.
    if resolve_provider(job.request) != provider:
        raise JobError("job_provider_changed", 403)
    files = tuple(sorted(p for p in directory.iterdir() if p.is_file()))
    ref = GCSArtifactStore(
        os.environ["LNF_JOB_ARTIFACT_BUCKET"], root
    ).publish_manifest(job, files, job.fencing_token)
    send({"kind": "result", "ref": ref.model_dump(mode="json")})


def main() -> int:
    channel = sys.stdout

    def send(event):
        channel.write(json.dumps(event, separators=(",", ":")) + "\n")
        channel.flush()

    try:
        # Only the bounded protocol uses stdout. Generator/library diagnostics
        # cannot grow a log buffer or leak provider payloads into durable events.
        with contextlib.redirect_stdout(sys.stderr):
            if sys.argv[1:] == ["--reconcile"]:
                from langgraph_system_generator.api.worker_server import (
                    configured_reconciler,
                )

                from .gcs_artifacts import GCSArtifactStore
                from .retention import RetentionCleaner

                reconciler = configured_reconciler()
                counts = reconciler.reconcile_once(pages=2, seconds=15)
                counts.update(
                    RetentionCleaner(
                        reconciler.store,
                        GCSArtifactStore(
                            os.environ["LNF_JOB_ARTIFACT_BUCKET"], Path.cwd()
                        ),
                    ).sweep()
                )
                send(counts)
            else:
                raw = sys.stdin.buffer.readline(131073)
                if len(raw) > 131072:
                    raise JobError("attempt_payload_invalid", 400)
                asyncio.run(generate(json.loads(raw), send))
        return 0
    except Exception as error:  # noqa: BLE001 - sanitized child protocol boundary
        status = getattr(error, "status", getattr(error, "status_code", 503))
        send(
            {
                "kind": "error",
                "permanent": isinstance(status, int) and 400 <= status < 500,
            }
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
