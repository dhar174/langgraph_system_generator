"""Credential redaction shared by generation and documentation transports."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_SECRET_FRAGMENT = re.compile(
    r"key|token|secret|password|auth|cred|signature", re.IGNORECASE
)
_NAME_TOKEN = re.compile(r"[\w-]+")


def _skip_whitespace(text: str, position: int) -> int:
    while position < len(text) and text[position].isspace():
        position += 1
    return position


def _redact_named_credentials(text: str) -> str:
    """Scan disjoint name tokens and values in O(n) work and O(n) space.

    Each maximal name is checked against a fixed number of secret fragments.
    Delimiter lookahead covers only adjacent whitespace. Consumed values are
    skipped, and unchanged slices are joined once. Unterminated quoted secrets
    consume the remaining diagnostic rather than exposing a partial value.
    """
    pieces: list[str] = []
    copied_until = 0
    for match in _NAME_TOKEN.finditer(text):
        if match.start() < copied_until:
            continue
        if _SECRET_FRAGMENT.search(match.group()) is None:
            continue
        position = match.end()
        if (
            match.start() > 0
            and text[match.start() - 1] in "\"'"
            and position < len(text)
            and text[position] in "\"'"
        ):
            position = _skip_whitespace(text, position + 1)
            if position == len(text) or text[position] != ":":
                continue
        else:
            position = _skip_whitespace(text, position)
            if position == len(text) or text[position] != "=":
                continue
        position = _skip_whitespace(text, position + 1)
        if position == len(text):
            continue
        if text[position] in "\"'":
            quote = text[position]
            value_start = position + 1
            value_end = value_start
            while value_end < len(text) and text[value_end] != quote:
                value_end += 2 if text[value_end] == "\\" else 1
            value_end = min(value_end, len(text))
        else:
            value_start = position
            value_end = position
            while (
                value_end < len(text)
                and not text[value_end].isspace()
                and text[value_end] not in "&,'\"<>"
            ):
                value_end += 1
        if value_end == value_start:
            continue
        pieces.extend((text[copied_until:value_start], "[REDACTED]"))
        copied_until = value_end
    pieces.append(text[copied_until:])
    return "".join(pieces)


class _LLMDiagnosticFilter(logging.Filter):
    """Keep SDK/HTTP diagnostics useful without logging endpoints or bodies."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        # SDK/HTTPcore diagnostic formats are not a stable allowlist. Ordinary
        # remote header names can contain echoed credentials, and exceptions
        # can include raw wire data. Keep these payloads out of logs entirely.
        if record.name.startswith("openai"):
            message = "LLM SDK diagnostic details omitted."
        elif record.name.startswith("httpcore"):
            message = "LLM HTTP transport diagnostic details omitted."
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
    # Logger filters do not apply to descendant records. Attach directly to
    # every emitting HTTPcore logger used by the supported sync/async transport.
    for name in (
        "httpx",
        "openai._base_client",
        "httpcore.connection",
        "httpcore.http11",
        "httpcore.http2",
        "httpcore.proxy",
        "httpcore.socks",
    ):
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
    """Redact URL credentials; omit malformed URLs whose fields cannot be parsed."""
    if not url:
        return ""
    url_str = str(url)
    try:
        prefix, separator, remainder = url_str.partition("//")
        authority = re.split(r"[/?#]", remainder, maxsplit=1)[0]
        safe_userinfo = ""
        if separator and "@" in authority:
            userinfo, _, host = authority.rpartition("@")
            safe_userinfo = (
                userinfo.split(":", 1)[0] + ":[REDACTED]@"
                if ":" in userinfo
                else "[REDACTED]@"
            )
            url_str = prefix + separator + remainder[len(userinfo) + 1 :]
        parts = urlsplit(url_str)
        netloc = safe_userinfo + parts.netloc
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
        return "[invalid URL omitted]"


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
        stripped_url = raw_url.rstrip("')]},;.:\"")
        return _sanitize_url_for_logging(stripped_url) + raw_url[len(stripped_url) :]

    result = re.sub(r"https?://[^\s<>'\"]+", _replace_url, result)

    # 3. Redact Bearer tokens
    result = re.sub(
        r"(bearer\s+)[A-Za-z0-9_\-\.]+",
        r"\1[REDACTED]",
        result,
        flags=re.IGNORECASE,
    )

    result = _redact_named_credentials(result)

    # 6. Redact basic-auth credentials in any remaining URL/netloc patterns
    result = re.sub(
        r"(://[^:/@\s]+:)[^@\s/]+@",
        r"\1[REDACTED]@",
        result,
    )

    return result
