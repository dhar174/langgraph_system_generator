"""Credential redaction shared by generation and documentation transports."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class _LLMDiagnosticFilter(logging.Filter):
    """Keep SDK/HTTP diagnostics useful without logging endpoints or bodies."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if record.name.startswith("openai") and any(
            marker in message.lower()
            for marker in ("request options", "response_headers", "request_id")
        ):
            message = "LLM SDK diagnostic details omitted."
        record.msg = sanitize_generation_payload(message)
        record.args = ()
        if record.exc_info:
            exception_type = record.exc_info[0]
            if exception_type is not None:
                record.msg += " (" + exception_type.__name__ + ")"
            record.exc_info = None
            record.exc_text = None
        return True


def install_llm_log_redaction() -> None:
    """Install stateless filters, including for callers without CLI logging setup."""
    for name in ("httpx", "openai._base_client"):
        logger = logging.getLogger(name)
        if not any(isinstance(item, _LLMDiagnosticFilter) for item in logger.filters):
            logger.addFilter(_LLMDiagnosticFilter())


def sanitize_generation_payload(value: Any) -> Any:
    """Redact nested diagnostics, including complete endpoint URLs and secrets.

    Documentation provenance keeps its existing URL sanitizer. Generation error
    payloads do not need raw endpoint URLs to explain their error classification.
    """
    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED]"
                if isinstance(item, str)
                and any(
                    part in str(key).lower()
                    for part in ("key", "secret", "password", "authorization", "token")
                )
                else sanitize_generation_payload(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_generation_payload(item) for item in value]
    if isinstance(value, str):
        return re.sub(
            r"https?://[^\s<>'\"]+", "[endpoint]", _sanitize_text_credentials(value)
        )
    return value


def _sanitize_header_for_logging(headers: dict[str, str]) -> dict[str, str]:
    """Return a copy of headers with secrets redacted."""
    safe = {}
    for k, v in headers.items():
        if k.lower() in ("authorization", "x-api-key", "api-key", "token"):
            safe[k] = "[REDACTED]"
        else:
            safe[k] = v
    return safe


def _sanitize_url_for_logging(url: str) -> str:
    """Redact sensitive query params and basic auth credentials from a URL string."""
    if not url:
        return ""
    url_str = str(url)
    try:
        parts = urlsplit(url_str)
        netloc = parts.netloc
        if "@" in netloc:
            userinfo, host = netloc.split("@", 1)
            if ":" in userinfo:
                user, _ = userinfo.split(":", 1)
                netloc = f"{user}:[REDACTED]@{host}"
            else:
                netloc = f"[REDACTED]@{host}"

        if parts.query:
            query_pairs = parse_qsl(parts.query, keep_blank_values=True)
            sanitized_pairs = []
            sensitive_fragments = (
                "key",
                "token",
                "secret",
                "password",
                "auth",
                "cred",
                "signature",
            )
            for k, v in query_pairs:
                k_lower = k.lower()
                if any(s in k_lower for s in sensitive_fragments):
                    sanitized_pairs.append((k, "[REDACTED]"))
                else:
                    sanitized_pairs.append((k, v))
            query = urlencode(sanitized_pairs, safe="[]")
        else:
            query = parts.query

        return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))
    except Exception:  # noqa: BLE001 - malformed URLs still need redaction
        # Fallback to regex if urlsplit/parse fails
        sanitized = re.sub(
            r"((?:[?&]|\b)[\w\-]*(?:key|token|secret|password|auth|cred|signature)[\w\-]*=)[^&\s]+",
            r"\1[REDACTED]",
            url_str,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            r"(://[^:/@\s]+:)[^@\s/]+@",
            r"\1[REDACTED]@",
            sanitized,
        )
        return sanitized


def _sanitize_text_credentials(text: Any, endpoint: str | None = None) -> str:
    """Sanitize error, warning, or payload text by redacting embedded URLs, compound secrets, and credentials."""
    if not text:
        return ""
    result = str(text)

    # 1. If an explicit endpoint was passed, redact it first
    if endpoint and endpoint in result:
        result = result.replace(endpoint, _sanitize_url_for_logging(endpoint))

    # 2. Extract and route all embedded URLs through _sanitize_url_for_logging
    def _replace_url(match: re.Match) -> str:
        raw_url = match.group(0)
        trailing = ""
        while raw_url and raw_url[-1] in "')]},;.:\"":
            trailing = raw_url[-1] + trailing
            raw_url = raw_url[:-1]
        return _sanitize_url_for_logging(raw_url) + trailing

    result = re.sub(r"https?://[^\s<>'\"]+", _replace_url, result)

    # 3. Redact Bearer tokens
    result = re.sub(
        r"(bearer\s+)[A-Za-z0-9_\-\.]+",
        r"\1[REDACTED]",
        result,
        flags=re.IGNORECASE,
    )

    # 4. Redact query/key-value tokens matching compound secret names (access_token, client_secret, etc.)
    result = re.sub(
        r"((?:[?&]|\b)[\w\-]*(?:key|token|secret|password|auth|cred|signature)[\w\-]*\s*=\s*)[^&\s,'\"<>]+",
        r"\1[REDACTED]",
        result,
        flags=re.IGNORECASE,
    )

    # 5. Redact JSON/dict style key-value pairs with compound secret names
    result = re.sub(
        r'(["\'][\w\-]*(?:key|token|secret|password|auth|cred|signature)[\w\-]*["\']\s*:\s*["\'])[^"\']+',
        r"\1[REDACTED]",
        result,
        flags=re.IGNORECASE,
    )

    # 6. Redact basic-auth credentials in any remaining URL/netloc patterns
    result = re.sub(
        r"(://[^:/@\s]+:)[^@\s/]+@",
        r"\1[REDACTED]@",
        result,
    )

    return result
