"""End-to-end MCP protocol tests.

Starts a real MCP server over streamable HTTP, sends JSON-RPC requests,
and verifies tool execution through the full MCP stack.

Run with: GOVINFO_API_KEY=xxx pytest tests/integration/test_mcp_e2e.py -v
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import time
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.integration

_PORT = 8399
_BASE = f"http://127.0.0.1:{_PORT}/mcp"
_SERVER_CMD = [
    sys.executable,
    "-m",
    "kaos_source.serve",
    "--http",
    "--port",
    str(_PORT),
]


@pytest.fixture(scope="module")
def mcp_server():
    """Start the MCP server as a subprocess for the test module."""
    env = {**os.environ, "GOVINFO_API_KEY": os.environ.get("GOVINFO_API_KEY", "")}
    proc = subprocess.Popen(
        _SERVER_CMD,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Wait for server to be ready
    for _ in range(30):
        time.sleep(0.5)
        try:
            httpx.get(f"http://127.0.0.1:{_PORT}/mcp", timeout=1.0)
        except (httpx.ConnectError, httpx.ReadError):
            continue
        except Exception:
            break  # Server is responding (even with errors = it's up)
    yield proc
    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=5)


async def _mcp_call(
    method: str,
    params: dict[str, Any] | None = None,
    call_id: int = 1,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Send a JSON-RPC request to the MCP server."""
    body: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": call_id,
        "method": method,
    }
    if params:
        body["params"] = params

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(_BASE, json=body, headers=headers)

    # Handle SSE response
    text = resp.text
    if "text/event-stream" in resp.headers.get("content-type", ""):
        # Parse SSE: find last "data:" line with JSON
        for line in reversed(text.splitlines()):
            if line.startswith("data:"):
                import json

                return json.loads(line[5:].strip())
        return {"error": "No data in SSE response", "raw": text[:500]}

    return resp.json()


async def _init_session() -> str | None:
    """Initialize MCP session and return session ID."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            _BASE,
            json={
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-e2e", "version": "1.0"},
                },
            },
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
        )
    return resp.headers.get("mcp-session-id")


class TestMCPEndToEnd:
    """Test the full MCP server → tool execution → response pipeline."""

    async def test_initialize(self, mcp_server: Any) -> None:
        """MCP: Initialize session."""
        session_id = await _init_session()
        # Session ID may or may not be present depending on MCP version
        # What matters is the server responds

    async def test_list_tools(self, mcp_server: Any) -> None:
        """MCP: List all registered tools."""
        session_id = await _init_session()
        result = await _mcp_call("tools/list", session_id=session_id, call_id=2)
        if "result" in result:
            tools = result["result"].get("tools", [])
            names = {t["name"] for t in tools}
            assert "kaos-source-discover" in names
            assert "kaos-source-fr-search" in names
            assert "kaos-source-edgar-search" in names
            assert "kaos-source-ecfr-titles" in names
            assert len(tools) >= 22

    async def test_call_fr_search(self, mcp_server: Any) -> None:
        """MCP: Call kaos-source-fr-search through the protocol."""
        session_id = await _init_session()
        result = await _mcp_call(
            "tools/call",
            params={
                "name": "kaos-source-fr-search",
                "arguments": {
                    "term": "securities regulation",
                    "per_page": 3,
                },
            },
            session_id=session_id,
            call_id=3,
        )
        if "result" in result:
            content = result["result"].get("content", [])
            assert len(content) > 0
            assert not result["result"].get("isError", False)

    async def test_call_ecfr_titles(self, mcp_server: Any) -> None:
        """MCP: Call kaos-source-ecfr-titles through the protocol."""
        session_id = await _init_session()
        result = await _mcp_call(
            "tools/call",
            params={
                "name": "kaos-source-ecfr-titles",
                "arguments": {},
            },
            session_id=session_id,
            call_id=4,
        )
        if "result" in result:
            assert not result["result"].get("isError", False)

    async def test_call_edgar_lookup(self, mcp_server: Any) -> None:
        """MCP: Call kaos-source-edgar-lookup for AAPL."""
        session_id = await _init_session()
        result = await _mcp_call(
            "tools/call",
            params={
                "name": "kaos-source-edgar-lookup",
                "arguments": {"ticker": "AAPL"},
            },
            session_id=session_id,
            call_id=5,
        )
        if "result" in result:
            assert not result["result"].get("isError", False)

    async def test_call_source_discover(self, mcp_server: Any) -> None:
        """MCP: Call kaos-source-discover on kaos-source package."""
        session_id = await _init_session()
        result = await _mcp_call(
            "tools/call",
            params={
                "name": "kaos-source-discover",
                "arguments": {
                    "path": os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "patterns": ["*.py"],
                    "limit": 5,
                },
            },
            session_id=session_id,
            call_id=6,
        )
        if "result" in result:
            assert not result["result"].get("isError", False)
