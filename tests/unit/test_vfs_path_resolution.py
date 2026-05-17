"""Regression tests for Stage 4 of the vfs-blind-tools-audit-and-fix plan.

Every file-input MCP tool in kaos-source now routes through
:func:`kaos_source._path_resolver.resolve_source_input` (a thin wrapper
around :func:`kaos_core.path_resolver.resolve_input_path`). Before
Stage 4, agent-supplied paths went through raw ``Path(p).exists()``
checks that could not see files uploaded into a session VFS by a UI
host. The agent therefore had no choice but to fabricate answers or
return brittle "File not found" errors.

These tests pin the new behaviour:

1. A file uploaded into the session VFS is visible to
   ``kaos-source-parse-eml`` using its bare VFS-relative path.
2. An archive uploaded into the session VFS is visible to
   ``kaos-source-inspect-archive`` using its bare VFS-relative path.
3. ``kaos-source-fetch-url`` short-circuits on ``kaos://`` URIs with
   an agent-friendly error that names *both* kaos-source-materialize
   *and* the kaos-content-* tool family as alternatives (SES2 fix
   for issue #402). It still rejects unsupported schemes (ftp://) and
   still accepts http(s):// URLs.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from kaos_core import (
    ArtifactStore,
    KaosContext,
    KaosRuntime,
    KaosSettings,
    VFSConfig,
    VirtualFileSystem,
)
from kaos_core.types.enums import StorageBackend

from kaos_source.parsers.email.tools import ParseEmlTool
from kaos_source.runtime.tools import FetchURLTool, InspectArchiveTool

# ---------------------------------------------------------------------------
# Helpers — mirror kaos-core's path_resolver test harness so the VFS /
# ArtifactStore wiring is identical to what the SPA backend uses.
# ---------------------------------------------------------------------------


def _make_runtime(tmp_path: Path) -> KaosRuntime:
    settings = KaosSettings(
        artifact_inline_read_max_bytes=262_144,
        artifact_chunk_size_bytes=64,
    )
    runtime = KaosRuntime(config=settings)
    runtime.vfs = VirtualFileSystem(
        VFSConfig(default_backend=StorageBackend.DISK, disk_base_path=tmp_path / "vfs")
    )
    runtime.artifacts = ArtifactStore(
        runtime.vfs,
        manifest_context_id=settings.artifact_manifest_context_id,
        manifest_prefix=settings.artifact_manifest_prefix,
        max_inline_read_bytes=settings.artifact_inline_read_max_bytes,
        default_chunk_size=settings.artifact_chunk_size_bytes,
        temporary_ttl_seconds=settings.artifact_temporary_ttl_seconds,
    )
    return runtime


@pytest.fixture()
def vfs_runtime(tmp_path: Path) -> KaosRuntime:
    return _make_runtime(tmp_path)


@pytest.fixture()
def vfs_ctx(vfs_runtime: KaosRuntime) -> KaosContext:
    return KaosContext(session_id="s-vfs", runtime=vfs_runtime, vfs=vfs_runtime.vfs)


# Smallest possible RFC 5322 message that exercises every field
# ParseEmlTool's summary builder reads (from / subject / attachments).
_FAKE_EML = (
    b"From: sender@example.test\r\n"
    b"To: recipient@example.test\r\n"
    b"Subject: Stage 4 VFS smoke test\r\n"
    b"Message-ID: <stage4-smoke@example.test>\r\n"
    b"Date: Sat, 17 May 2026 00:00:00 +0000\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"\r\n"
    b"Body content for the VFS smoke test.\r\n"
)


# ---------------------------------------------------------------------------
# 1. Parse-eml resolves VFS-uploaded files
# ---------------------------------------------------------------------------


async def test_parse_eml_reads_vfs_uploaded_file(vfs_ctx: KaosContext) -> None:
    """A bare VFS-relative path must reach the eml parser.

    Mirrors the SPA's single-user-chat upload path layout:
    ``backend/.kaos-vfs/sessions/<sid>/files/<name>.eml``. Before
    Stage 4 this returned ``File not found`` because the tool called
    ``Path(p).exists()`` directly.
    """
    vfs_path = "files/stage4_smoke.eml"
    handle = vfs_ctx.get_vfs_path(vfs_path)
    await handle.write_bytes(_FAKE_EML)

    tool = ParseEmlTool()
    result = await tool.execute({"path": vfs_path}, vfs_ctx)

    assert not result.isError, result.text
    assert result.structuredContent is not None
    assert result.structuredContent["subject"] == "Stage 4 VFS smoke test"
    assert result.structuredContent["from_address"]["address"] == "sender@example.test"


# ---------------------------------------------------------------------------
# 2. Inspect-archive returns the member list when the archive lives in VFS
# ---------------------------------------------------------------------------


async def test_inspect_archive_reads_vfs_uploaded_archive(vfs_ctx: KaosContext) -> None:
    """A small ZIP uploaded into the VFS must be enumerable by the tool."""
    archive_bytes_path = Path(vfs_ctx.session_id) / "tmp-test.zip"
    del archive_bytes_path  # silence unused — we only need the in-memory bytes below

    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("readme.txt", "Stage 4 smoke")
        zf.writestr("data/payload.csv", "a,b\n1,2\n")
    archive_bytes = buffer.getvalue()

    vfs_path = "files/stage4_smoke.zip"
    handle = vfs_ctx.get_vfs_path(vfs_path)
    await handle.write_bytes(archive_bytes)

    tool = InspectArchiveTool()
    result = await tool.execute({"path": vfs_path}, vfs_ctx)

    assert not result.isError, result.text
    assert result.structuredContent is not None
    member_names = {m["name"] for m in result.structuredContent["members"]}
    # ZIP members are listed by basename in the existing
    # FilesystemConnector descriptor surface.
    assert any("readme.txt" in name for name in member_names)
    assert any("payload.csv" in name for name in member_names)


# ---------------------------------------------------------------------------
# 3. fetch-url SES2 — clean refusal on kaos:// URIs
# ---------------------------------------------------------------------------


async def test_fetch_url_refuses_kaos_artifact_uri_with_agent_guidance(
    vfs_ctx: KaosContext,
) -> None:
    """``kaos://artifacts/<id>`` was previously rejected with a bare
    "must use http or https" message that left the agent guessing.
    The SES2 fix returns an agent-friendly error that names both
    `kaos-source-materialize` and the `kaos-content-*` family as
    correct alternatives.
    """
    tool = FetchURLTool()
    result = await tool.execute(
        {"url": "kaos://artifacts/00000000-0000-0000-0000-000000000000"},
        vfs_ctx,
    )
    assert result.isError
    text = (result.text or "").lower()
    assert "kaos-source-materialize" in text
    assert "kaos-content" in text
    # Must NOT just regurgitate the original "http or https" complaint.
    assert "http or https" not in text


async def test_fetch_url_refuses_bare_kaos_vfs_uri_with_agent_guidance(
    vfs_ctx: KaosContext,
) -> None:
    """``kaos://workspace/notes.txt`` (bare VFS URI) hits the same
    SES2 short-circuit — the user wants to read a VFS file, not fetch
    HTTP, so we name the right tools instead of the URL validator's
    raw complaint.
    """
    tool = FetchURLTool()
    result = await tool.execute({"url": "kaos://workspace/notes.txt"}, vfs_ctx)
    assert result.isError
    text = (result.text or "").lower()
    assert "kaos-source-materialize" in text
    assert "kaos-content" in text


async def test_fetch_url_still_rejects_ftp(vfs_ctx: KaosContext) -> None:
    """Existing scheme guard must still trip for non-HTTP, non-kaos URLs."""
    tool = FetchURLTool()
    result = await tool.execute({"url": "ftp://example.com/file"}, vfs_ctx)
    assert result.isError
    assert "http" in (result.text or "").lower()


async def test_fetch_url_still_accepts_http_scheme(vfs_ctx: KaosContext) -> None:
    """HTTP URLs continue to flow through the existing materialization
    path — only the connection to a non-listening port fails, which
    proves the kaos:// short-circuit did not break http://.
    """
    tool = FetchURLTool()
    # 127.0.0.1 on an unlikely port: the SourceLocator.http(...) check
    # must accept the URL (no scheme rejection), and the failure must
    # come from the downstream materialize step, not the URL guard.
    result = await tool.execute({"url": "http://127.0.0.1:19999/test"}, vfs_ctx)
    assert result.isError
    text = (result.text or "").lower()
    # The error must come from the fetch/materialize step, not the
    # scheme guard. The existing message includes "browser" / "kaos-web".
    assert "kaos-source-materialize" not in text
    assert "http or https" not in text
