"""Storage selection is independent of user authorization and async admission."""

import json
import os
import re
from collections.abc import Mapping

from .models import JobError
from .protocols import JobStore


def backend_name(environ: Mapping[str, str] | None = None) -> str:
    values = os.environ if environ is None else environ
    name = values.get("LNF_JOB_BACKEND", "ephemeral")
    if name not in {"ephemeral", "firestore"}:
        raise JobError("job_backend_invalid", 503)
    return name


def select_job_store(environ: Mapping[str, str] | None = None) -> JobStore | None:
    """None explicitly selects existing Phase A. Never fall back after failure."""
    values = os.environ if environ is None else environ
    if backend_name(values) == "ephemeral":
        return None
    project = values.get("LNF_JOB_GCP_PROJECT", "")
    database = values.get("LNF_JOB_FIRESTORE_DATABASE", "(default)")
    secret = values.get("LNF_JOB_IDEMPOTENCY_SECRET", "").encode("utf-8")
    try:
        refs = json.loads(values.get("LNF_JOB_PROVIDER_REFS", '["openai-v1"]'))
        if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
            raise ValueError("invalid references")
        provider_refs = frozenset(refs)
    except (ValueError, TypeError):
        raise JobError("job_configuration_invalid", 503) from None
    if (
        not re.fullmatch(r"[a-z][a-z0-9-]{4,61}[a-z0-9]", project)
        or not re.fullmatch(r"\(default\)|[a-z][a-z0-9-]{2,62}", database)
        or len(secret) < 32
    ):
        raise JobError("job_configuration_invalid", 503)
    from .firestore_store import FirestoreJobStore

    return FirestoreJobStore(
        project, secret, database, approved_provider_refs=provider_refs
    )


def require_ephemeral_admission() -> None:
    """B1 has no public durable executor. Explicit durable config fails closed."""
    if backend_name() != "ephemeral":
        raise JobError("durable_admission_disabled", 503)
