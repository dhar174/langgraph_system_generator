"""Authorize LLM destinations separately from resolving runtime credentials.

No DNS preflight is performed: registered DNS names, TLS and network egress are
administrator trust assumptions, not a claim of connection-time IP pinning.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from langgraph_system_generator.utils.config import settings
from langgraph_system_generator.utils.error_handling import GenerationError

EndpointPolicy = Literal["local", "hosted"]
OPENAI_BASE = "https://api.openai.com/v1"
NO_AUTH_KEY = "lnf-local-no-auth"


def _error(message: str, code: str, status: int = 400) -> GenerationError:
    return GenerationError(
        message, code=code, phase="endpoint_policy", status_code=status
    )


def effective_policy(requested: EndpointPolicy = "local") -> EndpointPolicy:
    configured = os.getenv("LNF_LLM_ENDPOINT_POLICY", settings.lnf_llm_endpoint_policy)
    if configured not in {"local", "hosted"} or requested not in {"local", "hosted"}:
        raise _error(
            "LLM endpoint policy configuration is invalid.",
            "endpoint_policy_unavailable",
            503,
        )
    return "hosted" if "hosted" in (configured, requested) else "local"


def canonical_endpoint(value: str, *, hosted: bool) -> str:
    """Accept an intentionally narrow, unambiguous OpenAI-compatible base URL."""
    invalid = _error("Invalid LLM endpoint URL.", "invalid_endpoint")
    if not isinstance(value, str) or not value or not value.isascii():
        raise invalid
    if any(char.isspace() or ord(char) < 33 or ord(char) == 127 for char in value):
        raise invalid
    if any(char in value for char in "\\%@?#"):
        raise invalid
    try:
        parts = urlsplit(value)
        host = parts.hostname
        port = parts.port
    except ValueError:
        raise invalid from None
    if parts.scheme not in {"http", "https"} or not host or not parts.netloc:
        raise invalid
    if parts.netloc.endswith(":") or host.endswith("."):
        raise invalid
    if port is not None and not 1 <= port <= 65535:
        raise invalid
    host = host.lower()
    address = None
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        labels = host.split(".")
        if not all(
            re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in labels
        ):
            raise invalid from None
        # Numeric/octal/hex shorthand must never be interpreted as a DNS name.
        if re.fullmatch(r"[0-9.]+", host) or any(
            label.startswith("0x") for label in labels
        ):
            raise invalid from None
        try:
            if (
                host.encode("ascii").decode("idna").encode("idna").decode("ascii")
                != host
            ):
                raise invalid
        except UnicodeError:
            raise invalid from None
        if len(host) > 253:
            raise invalid
    if isinstance(address, ipaddress.IPv6Address) and (
        address.ipv4_mapped
        or not re.fullmatch(r"\[[0-9a-fA-F:]+\](?::[0-9]+)?", parts.netloc)
    ):
        raise invalid
    loopback = bool(address and address.is_loopback) or host == "localhost"
    if hosted:
        local_name = (
            host == "localhost"
            or host.endswith((".localhost", ".local", ".internal"))
            or "." not in host
            and address is None
        )
        if (
            parts.scheme != "https"
            or local_name
            or address is not None
            and (not address.is_global or address.is_multicast or address.is_reserved)
        ):
            raise _error(
                "LLM endpoint is not permitted by hosted policy.",
                "endpoint_not_allowed",
                403,
            )
    elif parts.scheme != "https" and not loopback:
        raise invalid
    path = parts.path
    if "//" in path or any(segment in {".", ".."} for segment in path.split("/")):
        raise invalid
    if not re.fullmatch(r"[/a-zA-Z0-9._~-]*", path):
        raise invalid
    path = path.removesuffix("/")
    if address is not None:
        host = address.compressed
    authority = f"[{host}]" if ":" in host else host
    if port is not None and port != (443 if parts.scheme == "https" else 80):
        authority += f":{port}"
    return urlunsplit((parts.scheme, authority, path, "", ""))


@dataclass(frozen=True)
class EndpointBinding:
    """Non-secret authorization result; credentials are resolved only at runtime."""

    provider_id: str
    base_url: str
    policy: EndpointPolicy
    api_key_env: str

    def credential(self) -> str:
        """Resolve only this binding's credential; never delegate to SDK fallback."""
        if self.provider_id == "openai":
            key = os.getenv("OPENAI_API_KEY", settings.openai_api_key or "")
        elif self.provider_id == "local-custom":
            key_setting = settings.lnf_custom_llm_api_key
            key = os.getenv(
                self.api_key_env, key_setting.get_secret_value() if key_setting else ""
            )
            no_auth_raw = os.getenv("LNF_CUSTOM_LLM_NO_AUTH")
            if no_auth_raw is not None and no_auth_raw.lower() not in {
                "true",
                "false",
                "1",
                "0",
            }:
                raise _error(
                    "Local LLM authentication configuration is invalid.",
                    "endpoint_policy_unavailable",
                    503,
                )
            no_auth = (
                settings.lnf_custom_llm_no_auth
                if no_auth_raw is None
                else no_auth_raw.lower() in {"true", "1"}
            )
            if no_auth:
                host = urlsplit(self.base_url).hostname or ""
                try:
                    loopback = ipaddress.ip_address(host).is_loopback
                except ValueError:
                    loopback = host == "localhost"
                if key or not loopback:
                    raise _error(
                        "No-auth requires a loopback endpoint and no configured custom key.",
                        "endpoint_policy_unavailable",
                        503,
                    )
                return NO_AUTH_KEY
        else:
            key = os.getenv(self.api_key_env, "")
        if not key or not key.strip():
            raise GenerationError(
                "Required LLM provider credentials are unavailable.",
                code="credentials_required",
                phase="endpoint_policy",
                status_code=503,
                hint=f"Configure {self.api_key_env} for {self.provider_id}.",
            )
        return key


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate configuration key")
        result[key] = value
    return result


def _registry() -> dict[str, tuple[str, str]]:
    raw = os.getenv("LNF_TRUSTED_LLM_ENDPOINTS", settings.lnf_trusted_llm_endpoints)
    result: dict[str, tuple[str, str]] = {}
    try:
        entries = json.loads(raw, object_pairs_hook=_unique_object)
        if not isinstance(entries, dict):
            raise TypeError("registry must be an object")
        for provider, definition in entries.items():
            if not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", provider) or provider in {
                "openai",
                "local-custom",
            }:
                raise ValueError("invalid provider id")
            if not isinstance(definition, dict) or set(definition) != {
                "base_url",
                "api_key_env",
            }:
                raise ValueError("invalid provider definition")
            key_env = definition["api_key_env"]
            if not isinstance(key_env, str) or not re.fullmatch(
                r"LNF_LLM_[A-Z0-9_]+_API_KEY", key_env
            ):
                raise ValueError("dedicated credential source required")
            endpoint = canonical_endpoint(definition["base_url"], hosted=True)
            if endpoint == OPENAI_BASE or endpoint in result:
                raise ValueError("duplicate endpoint")
            result[endpoint] = (provider, key_env)
    except (ValueError, TypeError, GenerationError):
        raise _error(
            "Trusted LLM endpoint configuration is invalid.",
            "endpoint_policy_unavailable",
            503,
        ) from None
    return result


def authorize_endpoint(
    value: str | None, policy: EndpointPolicy = "local"
) -> EndpointBinding:
    """Authorize without reading any provider credential or creating a client."""
    resolved_policy = effective_policy(policy)
    registry = _registry() if resolved_policy == "hosted" else {}
    endpoint = (
        canonical_endpoint(value, hosted=resolved_policy == "hosted")
        if value
        else OPENAI_BASE
    )
    if endpoint == OPENAI_BASE:
        return EndpointBinding("openai", OPENAI_BASE, resolved_policy, "OPENAI_API_KEY")
    if resolved_policy == "hosted":
        if endpoint not in registry:
            raise _error(
                "Custom LLM endpoint is not registered by the administrator.",
                "endpoint_not_allowed",
                403,
            )
        provider, key_env = registry[endpoint]
        return EndpointBinding(provider, endpoint, resolved_policy, key_env)
    return EndpointBinding(
        "local-custom", endpoint, resolved_policy, "LNF_CUSTOM_LLM_API_KEY"
    )
