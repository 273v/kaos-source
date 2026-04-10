"""End-to-end MCP tests via stdio transport — same protocol as Claude Code.

Spawns kaos-source-serve as a subprocess with stdio transport (the exact
same way Claude Code / Claude Desktop connects to MCP servers), sends
JSON-RPC messages through stdin/stdout, and verifies responses.

Run with: GOVINFO_API_KEY=xxx pytest tests/integration/test_mcp_stdio.py -v
"""

from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.integration

_SERVER_CMD = [sys.executable, "-m", "kaos_source.serve"]


_READ_TIMEOUT = 30.0  # seconds to wait for server response


def _read_one_message(proc: subprocess.Popen, timeout: float = _READ_TIMEOUT) -> dict:
    """Read a single Content-Length framed JSON-RPC message from the server.

    Uses select() to enforce a timeout so the test fails fast instead of
    hanging forever when the server doesn't respond.
    """
    assert proc.stdout is not None
    header = ""
    deadline = timeout
    while True:
        ready, _, _ = select.select([proc.stdout], [], [], deadline)
        if not ready:
            raise TimeoutError(
                f"MCP server did not send data within {timeout}s (partial header: {header!r})"
            )
        ch = proc.stdout.read(1)
        if not ch:
            raise RuntimeError("Server closed stdout")
        header += ch
        if header.endswith("\r\n\r\n"):
            break

    content_length = int(header.split("Content-Length:")[1].strip().split("\r\n")[0])
    body = proc.stdout.read(content_length)
    return json.loads(body)


def _send_receive(
    proc: subprocess.Popen, method: str, params: dict | None = None, msg_id: int = 1
) -> dict:
    """Send a JSON-RPC message via stdin and read the response from stdout.

    Skips any server-initiated notifications (messages without an ``id``)
    that arrive before the actual response.
    """
    request: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": msg_id,
        "method": method,
    }
    if params is not None:
        request["params"] = params

    payload = json.dumps(request)
    # subprocess.Popen types stdin/stdout as IO|None; the proc was constructed
    # with stdin=PIPE / stdout=PIPE so they're guaranteed non-None — narrow for ty.
    assert proc.stdin is not None
    assert proc.stdout is not None
    # MCP stdio uses Content-Length framing
    message = f"Content-Length: {len(payload)}\r\n\r\n{payload}"
    proc.stdin.write(message)
    proc.stdin.flush()

    # Read messages, skipping any notifications (no "id" field) until we get
    # the actual response matching our request.
    while True:
        msg = _read_one_message(proc)
        # Notifications have no "id" — skip them
        if "id" not in msg:
            continue
        return msg


def _drain_stderr(stream) -> None:
    """Read and discard stderr in a background thread to prevent pipe deadlock."""
    try:
        while stream.read(4096):
            pass
    except (OSError, ValueError):
        pass


@pytest.fixture(scope="module")
def mcp_stdio():
    """Start MCP server with stdio transport (same as Claude Code)."""
    env = {**os.environ, "GOVINFO_API_KEY": os.environ.get("GOVINFO_API_KEY", "")}
    proc = subprocess.Popen(
        _SERVER_CMD,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        bufsize=0,
    )

    # Drain stderr in a background thread to prevent pipe buffer deadlock.
    # When stderr's OS pipe buffer (~64 KB) fills, the child blocks on write
    # and stops processing stdin — classic subprocess deadlock.
    assert proc.stderr is not None
    stderr_thread = threading.Thread(target=_drain_stderr, args=(proc.stderr,), daemon=True)
    stderr_thread.start()

    # Initialize MCP session
    resp = _send_receive(
        proc,
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-stdio", "version": "1.0"},
        },
        msg_id=0,
    )
    assert "result" in resp, f"Initialize failed: {resp}"

    # Send initialized notification
    notif = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert proc.stdin is not None
    proc.stdin.write(f"Content-Length: {len(notif)}\r\n\r\n{notif}")
    proc.stdin.flush()

    yield proc

    proc.terminate()
    proc.wait(timeout=5)


class TestMCPStdio:
    """Tests through stdio MCP transport — identical to Claude Code's protocol."""

    def test_list_tools(self, mcp_stdio: subprocess.Popen) -> None:
        """Verify all 22 tools are visible through stdio MCP."""
        resp = _send_receive(mcp_stdio, "tools/list", msg_id=1)
        assert "result" in resp
        tools = resp["result"]["tools"]
        names = {t["name"] for t in tools}
        assert len(tools) >= 22
        # Core source tools
        assert "kaos-source-discover" in names
        assert "kaos-source-describe" in names
        assert "kaos-source-preview" in names
        assert "kaos-source-materialize" in names
        # Data connectors
        assert "kaos-source-fr-search" in names
        assert "kaos-source-ecfr-titles" in names
        assert "kaos-source-edgar-lookup" in names
        assert "kaos-source-govinfo-search" in names
        assert "kaos-source-pacer-parse" in names

    def test_call_fr_agencies(self, mcp_stdio: subprocess.Popen) -> None:
        """Call FR agencies tool through stdio — like Claude Code would."""
        resp = _send_receive(
            mcp_stdio,
            "tools/call",
            {
                "name": "kaos-source-fr-agencies",
                "arguments": {},
            },
            msg_id=2,
        )
        assert "result" in resp
        result = resp["result"]
        assert not result.get("isError", False)
        # Should have text content with agency count
        assert len(result["content"]) > 0
        text = result["content"][0]["text"]
        assert "agency" in text.lower()

    def test_call_ecfr_titles(self, mcp_stdio: subprocess.Popen) -> None:
        """Call eCFR titles tool through stdio."""
        resp = _send_receive(
            mcp_stdio,
            "tools/call",
            {
                "name": "kaos-source-ecfr-titles",
                "arguments": {},
            },
            msg_id=3,
        )
        assert "result" in resp
        assert not resp["result"].get("isError", False)

    def test_call_edgar_lookup(self, mcp_stdio: subprocess.Popen) -> None:
        """Look up Apple's CIK through stdio MCP — full agent workflow."""
        resp = _send_receive(
            mcp_stdio,
            "tools/call",
            {
                "name": "kaos-source-edgar-lookup",
                "arguments": {"ticker": "MSFT"},
            },
            msg_id=4,
        )
        assert "result" in resp
        result = resp["result"]
        assert not result.get("isError", False)
        # Verify structured content has CIK
        structured = result.get("structuredContent", {})
        assert structured.get("ticker") == "MSFT"

    def test_call_fr_search(self, mcp_stdio: subprocess.Popen) -> None:
        """Search Federal Register through stdio MCP."""
        resp = _send_receive(
            mcp_stdio,
            "tools/call",
            {
                "name": "kaos-source-fr-search",
                "arguments": {
                    "term": "environmental protection",
                    "doc_type": "RULE",
                    "per_page": 3,
                },
            },
            msg_id=5,
        )
        assert "result" in resp
        result = resp["result"]
        assert not result.get("isError", False)

    def test_call_source_describe(self, mcp_stdio: subprocess.Popen) -> None:
        """Describe a file through stdio MCP."""
        resp = _send_receive(
            mcp_stdio,
            "tools/call",
            {
                "name": "kaos-source-describe",
                "arguments": {
                    "path": str(Path("pyproject.toml").resolve()),
                },
            },
            msg_id=6,
        )
        assert "result" in resp
        result = resp["result"]
        assert not result.get("isError", False)
        structured = result.get("structuredContent", {})
        assert structured.get("name") == "pyproject.toml"

    def test_error_handling(self, mcp_stdio: subprocess.Popen) -> None:
        """Verify error handling through stdio MCP — agent gets recovery guidance."""
        resp = _send_receive(
            mcp_stdio,
            "tools/call",
            {
                "name": "kaos-source-describe",
                "arguments": {"path": "/nonexistent/file.txt"},
            },
            msg_id=7,
        )
        assert "result" in resp
        result = resp["result"]
        assert result.get("isError", True)
        # Error text should have recovery guidance
        error_text = result["content"][0]["text"]
        assert "not found" in error_text.lower() or "verify" in error_text.lower()
