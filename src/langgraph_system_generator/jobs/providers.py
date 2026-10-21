"""Resolve approved symbolic references against current hosted endpoint policy."""

import json
import os
from dataclasses import dataclass

from langgraph_system_generator import __version__
from langgraph_system_generator.utils.llm_endpoint_security import authorize_endpoint

from .models import GenerationRequestEnvelope, JobError


@dataclass(frozen=True)
class ProviderResolution:
    endpoint: str | None
    provider_id: str
    credential_env: str


def resolve_provider(request: GenerationRequestEnvelope) -> ProviderResolution:
    try:
        bindings = json.loads(
            os.getenv("LNF_JOB_PROVIDER_BINDINGS", '{"openai-v1":"openai"}')
        )
        if (
            not isinstance(bindings, dict)
            or not 1 <= len(bindings) <= 32
            or any(
                not isinstance(k, str) or not isinstance(v, str)
                for k, v in bindings.items()
            )
        ):
            raise ValueError("invalid bindings")
        approved = json.loads(os.getenv("LNF_JOB_PROVIDER_REFS", '["openai-v1"]'))
        if (
            not isinstance(approved, list)
            or request.provider_ref not in approved
            or request.generator_version != __version__
            or request.provider_ref not in bindings
        ):
            raise JobError("job_provider_not_approved", 403)
        provider = bindings[request.provider_ref]
        endpoint = None
        if provider != "openai":
            registry = json.loads(os.getenv("LNF_TRUSTED_LLM_ENDPOINTS", "{}"))
            endpoint = registry[provider]["base_url"]
        binding = authorize_endpoint(endpoint, "hosted")
        if binding.provider_id != provider:
            raise JobError("job_provider_not_approved", 403)
        return ProviderResolution(endpoint, binding.provider_id, binding.api_key_env)
    except JobError:
        raise
    except Exception:  # noqa: BLE001 - redact registry and endpoint policy details
        # Never reflect registrations, URLs or credential variable names.
        raise JobError("job_provider_policy_invalid", 403) from None
