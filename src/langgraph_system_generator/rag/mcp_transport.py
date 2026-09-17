"""Shared Model Context Protocol (MCP) Streamable HTTP transport helper."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

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


def _parse_sse_response(text: str) -> Optional[Dict[str, Any]]:
    """Attempt to parse a Server-Sent Events (SSE) body for JSON payload."""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            data_str = line[len("data:") :].strip()
            if data_str:
                try:
                    parsed = json.loads(data_str)
                    if isinstance(parsed, dict):
                        return parsed
                except Exception:
                    pass
    return None


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
        raise MCPTransportError("No MCP endpoint URL provided", error_kind="configuration")
    endpoint = target_endpoint
    if arguments is None:
        arguments = {}
    if api_key and not authorization:
        authorization = api_key if api_key.startswith("Bearer ") else f"Bearer {api_key}"

    headers: Dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": protocol_version,
        "Mcp-Method": "tools/call",
        "Mcp-Name": tool_name,
    }
    if authorization:
        headers["Authorization"] = authorization

    json_rpc_payload: Dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
            "_meta": {
                "protocolVersion": protocol_version,
            },
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
            r'([?&](?:api_key|token|key|secret)=)[^&\s]+',
            r'\1[REDACTED]',
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
            r'([?&](?:api_key|token|key|secret)=)[^&\s]+',
            r'\1[REDACTED]',
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
        clean_preview = re.sub(
            r'(bearer\s+)[A-Za-z0-9_\-\.]+',
            r'\1[REDACTED]',
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
        sse_data = _parse_sse_response(response.text)
        if sse_data is not None:
            return sse_data

    # Standard JSON response
    try:
        data = response.json()
        if isinstance(data, dict):
            return data
        raise ValueError("MCP response did not decode to a JSON object")
    except Exception as json_err:
        # Check if response text has SSE format even without content-type header
        if "data:" in response.text:
            sse_data = _parse_sse_response(response.text)
            if sse_data is not None:
                return sse_data
        raise MCPTransportError(
            f"Invalid JSON response from MCP endpoint '{endpoint}'",
            error_kind="parse",
        ) from json_err
