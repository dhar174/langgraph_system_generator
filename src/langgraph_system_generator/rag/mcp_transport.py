"""Shared Model Context Protocol (MCP) Streamable HTTP transport helper."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

logger = logging.getLogger(__name__)

DEFAULT_MCP_PROTOCOL_VERSION = "2026-07-28"


class MCPTransportError(Exception):
    """Typed error raised during MCP tool invocation or transport communication."""

    def __init__(
        self,
        message: str,
        *,
        error_kind: str = "transport",
        status_code: Optional[int] = None,
        is_connection_error: bool = False,
        response_data: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_kind = error_kind
        self.status_code = status_code
        self.is_connection_error = is_connection_error
        self.response_data = response_data

    def __str__(self) -> str:
        return self.message


def _sanitize_header_for_logging(headers: Dict[str, str]) -> Dict[str, str]:
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
    except Exception:
        # Fallback to regex if urlsplit/parse fails
        sanitized = re.sub(
            r"((?:[?&]|\b)[\w\-]*(?:key|token|secret|password|auth|cred)[\w\-]*=)[^&\s]+",
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


def _id_matches(response_id: Any, request_id: Any) -> bool:
    """Check if a response ID matches the expected request ID."""
    if response_id is None or request_id is None:
        return False
    if response_id == request_id:
        return True
    return str(response_id) == str(request_id)


def _is_valid_jsonrpc_payload(data: Any, request_id: int | str) -> bool:
    """Determine whether data is a structured JSON-RPC response or error for request_id."""
    if not isinstance(data, dict):
        return False
    if not _id_matches(data.get("id"), request_id):
        return False
    if "jsonrpc" in data and data["jsonrpc"] != "2.0":
        return False
    # Must contain either 'result' or 'error' (JSON-RPC 2.0 response specification)
    if "result" not in data and "error" not in data:
        return False
    if "error" in data:
        err_obj = data["error"]
        if not isinstance(err_obj, (dict, str)):
            return False
    return True


def _parse_sse_response(
    text: str,
    request_id: Optional[int | str] = None,
) -> Dict[str, Any]:
    """Parse Server-Sent Events (SSE) body and return the matching JSON-RPC response.

    Consumes all SSE 'data:' events, ignores notification-only objects (e.g.
    'notifications/progress') with no matching response id, and returns the
    final JSON-RPC response matching `request_id`.

    Raises:
        MCPTransportError: If no valid matching response exists.
    """
    if not text or not text.strip():
        raise MCPTransportError(
            "Empty SSE response from MCP endpoint", error_kind="parse"
        )

    matched_response: Optional[Dict[str, Any]] = None
    found_any_data = False

    # Standard SSE events are separated by double newlines.
    # Also support single-event or back-to-back events without double newlines.
    blocks = re.split(r"\r?\n\r?\n+", text.strip())
    candidate_objects: List[Dict[str, Any]] = []

    for block in blocks:
        data_lines: List[str] = []
        for line in block.splitlines():
            stripped = line.strip()
            if stripped.startswith("data:"):
                found_any_data = True
                payload_part = line[line.find("data:") + len("data:") :]
                if payload_part.startswith(" "):
                    payload_part = payload_part[1:]
                data_lines.append(payload_part)

        if not data_lines:
            continue

        # Try parsing joined data lines first (standard SSE multi-line data)
        joined_data = "\n".join(data_lines).strip()
        parsed_block = False
        if joined_data:
            try:
                parsed = json.loads(joined_data)
                if isinstance(parsed, dict):
                    candidate_objects.append(parsed)
                    parsed_block = True
            except Exception:
                pass

        # If joined parsing failed, try each line individually (e.g. back-to-back single-line events)
        if not parsed_block and len(data_lines) > 1:
            for d_line in data_lines:
                d_line = d_line.strip()
                if not d_line:
                    continue
                try:
                    parsed = json.loads(d_line)
                    if isinstance(parsed, dict):
                        candidate_objects.append(parsed)
                except Exception:
                    pass

    # Find the final JSON-RPC response matching request_id
    for obj in candidate_objects:
        obj_id = obj.get("id")
        if request_id is not None:
            if _id_matches(obj_id, request_id):
                matched_response = obj
        else:
            if obj_id is not None or "result" in obj or "error" in obj:
                matched_response = obj

    if matched_response is not None:
        return matched_response

    if not found_any_data:
        # Check if text is plain JSON despite content-type header
        try:
            fallback_obj = json.loads(text.strip())
            if isinstance(fallback_obj, dict):
                obj_id = fallback_obj.get("id")
                if request_id is None or _id_matches(obj_id, request_id):
                    return fallback_obj
        except Exception:
            pass
        raise MCPTransportError(
            "No SSE 'data:' events found in response",
            error_kind="parse",
        )

    raise MCPTransportError(
        f"No valid JSON-RPC response matching request_id '{request_id}' found in SSE stream",
        error_kind="parse",
    )


async def call_mcp_tool(
    endpoint: Optional[str] = None,
    tool_name: str = "",
    arguments: Optional[Dict[str, Any]] = None,
    *,
    endpoint_url: Optional[str] = None,
    api_key: Optional[str] = None,
    authorization: Optional[str] = None,
    timeout_seconds: float = 5.0,
    protocol_version: str = DEFAULT_MCP_PROTOCOL_VERSION,
    request_id: int | str = 1,
) -> Dict[str, Any]:
    """Call a tool on an MCP Streamable HTTP endpoint.

    Follows the MCP Streamable HTTP specification:
      - Includes protocol headers: MCP-Protocol-Version, Mcp-Method, Mcp-Name.
      - Sets Accept: application/json, text/event-stream.
      - Carries protocol version in JSON-RPC params._meta.
      - Parses standard JSON and SSE event payloads.
      - Distinguishes network/connection failures from server/tool errors.
      - Never logs credentials.

    Args:
        endpoint: HTTP/HTTPS URL of the MCP server endpoint.
        tool_name: Name of the MCP tool to invoke.
        arguments: Tool arguments dictionary.
        authorization: Optional HTTP Authorization header value (e.g. 'Bearer ...').
        timeout_seconds: Network request timeout in seconds.
        protocol_version: MCP protocol version string (default: 2026-07-28).
        request_id: JSON-RPC request identifier.

    Returns:
        Parsed JSON-RPC response dictionary.

    Raises:
        MCPTransportError: On connection failure, HTTP error, or unparseable response.
    """
    try:
        import httpx
    except ImportError as exc:
        raise MCPTransportError(
            "Optional dependency 'httpx' is required for MCP HTTP transport.",
            error_kind="missing_dependency",
        ) from exc

    target_endpoint = endpoint or endpoint_url
    if not target_endpoint:
        raise MCPTransportError(
            "No MCP endpoint URL provided", error_kind="configuration"
        )
    endpoint = target_endpoint
    safe_endpoint = _sanitize_url_for_logging(endpoint)
    if arguments is None:
        arguments = {}
    if api_key and not authorization:
        authorization = (
            api_key if api_key.startswith("Bearer ") else f"Bearer {api_key}"
        )

    headers: Dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": protocol_version,
        "Mcp-Method": "tools/call",
        "Mcp-Name": tool_name,
    }
    if authorization:
        headers["Authorization"] = authorization

    meta_payload: Dict[str, Any] = {
        "io.modelcontextprotocol/protocolVersion": protocol_version,
        "io.modelcontextprotocol/clientCapabilities": {},
        "io.modelcontextprotocol/clientInfo": {
            "name": "langgraph-system-generator",
            "version": "1.0.0",
        },
    }

    json_rpc_payload: Dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
            "_meta": meta_payload,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                endpoint,
                json=json_rpc_payload,
                headers=headers,
            )
    except (
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.WriteTimeout,
        httpx.PoolTimeout,
        httpx.NetworkError,
        httpx.TimeoutException,
        httpx.ProxyError,
        httpx.UnsupportedProtocol,
    ) as req_err:
        # Sanitize error message to ensure no sensitive URL tokens or secrets leak
        err_text = re.sub(
            r"([?&][\w\-]*(?:key|token|secret|password|auth|cred)[\w\-]*=)[^&\s]+",
            r"\1[REDACTED]",
            str(req_err),
            flags=re.IGNORECASE,
        )
        raise MCPTransportError(
            f"MCP connection failed: {err_text}",
            error_kind="connection",
            is_connection_error=True,
        ) from req_err
    except Exception as exc:
        err_text = re.sub(
            r"([?&][\w\-]*(?:key|token|secret|password|auth|cred)[\w\-]*=)[^&\s]+",
            r"\1[REDACTED]",
            str(exc),
            flags=re.IGNORECASE,
        )
        raise MCPTransportError(
            f"MCP transport error: {err_text}",
            error_kind="transport",
            is_connection_error=False,
        ) from exc

    content_type = response.headers.get("content-type", "")

    if response.status_code != 200:
        # Non-200 response: attempt to extract structured JSON-RPC response/error
        parsed_payload: Optional[Dict[str, Any]] = None
        if "text/event-stream" in content_type:
            try:
                parsed_payload = _parse_sse_response(
                    response.text, request_id=request_id
                )
            except MCPTransportError:
                parsed_payload = None
        else:
            try:
                raw_json = response.json()
                if isinstance(raw_json, dict):
                    parsed_payload = raw_json
            except Exception:
                if "data:" in response.text:
                    try:
                        parsed_payload = _parse_sse_response(
                            response.text, request_id=request_id
                        )
                    except MCPTransportError:
                        parsed_payload = None

        if parsed_payload is not None and _is_valid_jsonrpc_payload(
            parsed_payload, request_id=request_id
        ):
            return parsed_payload

        clean_preview = re.sub(
            r"(bearer\s+)[A-Za-z0-9_\-\.]+",
            r"\1[REDACTED]",
            response.text[:200],
            flags=re.IGNORECASE,
        )
        raise MCPTransportError(
            f"MCP HTTP {response.status_code}: {clean_preview.strip()}",
            error_kind="http",
            status_code=response.status_code,
        )

    # Check for text/event-stream response
    if "text/event-stream" in content_type:
        return _parse_sse_response(response.text, request_id=request_id)

    # Standard JSON response
    try:
        data = response.json()
    except Exception as json_err:
        # Check if response text has SSE format even without content-type header
        if "data:" in response.text:
            return _parse_sse_response(response.text, request_id=request_id)
        raise MCPTransportError(
            f"Invalid JSON response from MCP endpoint '{safe_endpoint}'",
            error_kind="parse",
        ) from json_err

    if isinstance(data, dict) and _is_valid_jsonrpc_payload(
        data, request_id=request_id
    ):
        return data

    if "data:" in response.text and not isinstance(data, dict):
        return _parse_sse_response(response.text, request_id=request_id)

    raise MCPTransportError(
        f"Invalid JSON-RPC response for request_id '{request_id}' from MCP endpoint '{safe_endpoint}'",
        error_kind="parse",
    )
