"""Tests for kaos-source MCP tools."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from kaos_core import KaosContext, KaosRuntime

from kaos_source.tools import (
    DescribeSourceTool,
    DiscoverSourcesTool,
    FetchURLTool,
    InspectArchiveTool,
    MaterializeSourceTool,
    PreviewSourceTool,
    register_source_tools,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ctx(runtime: KaosRuntime) -> KaosContext:
    return KaosContext.create(session_id="test", runtime=runtime)


@pytest.fixture()
def sample_dir(tmp_path: Path) -> Path:
    """Create a directory with sample files for discovery tests."""
    d = tmp_path / "samples"
    d.mkdir()
    (d / "readme.txt").write_text("Hello World")
    (d / "data.csv").write_text("id,name\n1,Alice\n2,Bob\n")
    sub = d / "sub"
    sub.mkdir()
    (sub / "nested.pdf").write_bytes(b"%PDF-1.4 fake")
    return d


@pytest.fixture()
def sample_file(tmp_path: Path) -> Path:
    """Create a sample text file."""
    f = tmp_path / "hello.txt"
    f.write_text("Hello, this is a test file with some content for preview testing.")
    return f


@pytest.fixture()
def sample_archive(tmp_path: Path) -> Path:
    """Create a sample ZIP archive."""
    archive_path = tmp_path / "test.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("doc.txt", "Document content here.")
        zf.writestr("data/report.csv", "col1,col2\n1,2\n3,4\n")
        zf.writestr("images/photo.png", b"\x89PNG fake image data")
    return archive_path


@pytest.fixture()
def binary_file(tmp_path: Path) -> Path:
    """Create a binary file."""
    f = tmp_path / "binary.bin"
    f.write_bytes(bytes(range(256)))
    return f


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_source_tools(self, runtime: KaosRuntime) -> None:
        count = register_source_tools(runtime)
        assert count == 22  # 6 core + 4 FR + 4 eCFR + 3 GovInfo + 3 EDGAR + 2 PACER

    def test_register_source_tools_names(self, runtime: KaosRuntime) -> None:
        register_source_tools(runtime)
        names = {t.metadata.name for t in runtime.tools.list_tool_objects()}
        expected = {
            "kaos-source-discover",
            "kaos-source-describe",
            "kaos-source-preview",
            "kaos-source-materialize",
            "kaos-source-fetch-url",
            "kaos-source-inspect-archive",
        }
        assert expected.issubset(names)


# ---------------------------------------------------------------------------
# Annotations
# ---------------------------------------------------------------------------


class TestAnnotations:
    def test_discover_annotations(self) -> None:
        tool = DiscoverSourcesTool()
        ann = tool.metadata.annotations
        assert ann is not None
        assert ann.readOnlyHint is True
        assert ann.destructiveHint is False
        assert ann.idempotentHint is True
        assert ann.openWorldHint is False

    def test_describe_annotations(self) -> None:
        tool = DescribeSourceTool()
        ann = tool.metadata.annotations
        assert ann is not None
        assert ann.readOnlyHint is True

    def test_preview_annotations(self) -> None:
        tool = PreviewSourceTool()
        ann = tool.metadata.annotations
        assert ann is not None
        assert ann.readOnlyHint is True

    def test_materialize_annotations(self) -> None:
        tool = MaterializeSourceTool()
        ann = tool.metadata.annotations
        assert ann is not None
        assert ann.readOnlyHint is False  # writes artifact
        assert ann.destructiveHint is False

    def test_fetch_url_annotations(self) -> None:
        tool = FetchURLTool()
        ann = tool.metadata.annotations
        assert ann is not None
        assert ann.openWorldHint is True  # network access
        assert ann.readOnlyHint is False  # writes artifact

    def test_inspect_archive_annotations(self) -> None:
        tool = InspectArchiveTool()
        ann = tool.metadata.annotations
        assert ann is not None
        assert ann.readOnlyHint is True


# ---------------------------------------------------------------------------
# DiscoverSourcesTool
# ---------------------------------------------------------------------------


class TestDiscoverSources:
    async def test_discover_directory(self, ctx: KaosContext, sample_dir: Path) -> None:
        tool = DiscoverSourcesTool()
        result = await tool.execute({"path": str(sample_dir)}, ctx)
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["count"] >= 3

    async def test_discover_with_pattern(self, ctx: KaosContext, sample_dir: Path) -> None:
        tool = DiscoverSourcesTool()
        result = await tool.execute({"path": str(sample_dir), "patterns": ["*.txt"]}, ctx)
        assert not result.isError
        assert result.structuredContent is not None
        names = [item["name"] for item in result.structuredContent["items"]]
        assert "readme.txt" in names
        assert "data.csv" not in names

    async def test_discover_with_limit(self, ctx: KaosContext, sample_dir: Path) -> None:
        tool = DiscoverSourcesTool()
        result = await tool.execute({"path": str(sample_dir), "limit": 1}, ctx)
        assert not result.isError
        assert result.structuredContent is not None
        assert len(result.structuredContent["items"]) == 1

    async def test_discover_nonexistent_path(self, ctx: KaosContext) -> None:
        tool = DiscoverSourcesTool()
        result = await tool.execute({"path": "/nonexistent/path"}, ctx)
        assert result.isError
        assert "not found" in (result.text or "").lower()

    async def test_discover_file_not_dir(self, ctx: KaosContext, sample_file: Path) -> None:
        tool = DiscoverSourcesTool()
        result = await tool.execute({"path": str(sample_file)}, ctx)
        assert result.isError
        assert "kaos-source-describe" in (result.text or "")

    async def test_discover_archive_auto_detect(
        self, ctx: KaosContext, sample_archive: Path
    ) -> None:
        tool = DiscoverSourcesTool()
        result = await tool.execute({"path": str(sample_archive)}, ctx)
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["count"] >= 2

    async def test_discover_non_recursive(self, ctx: KaosContext, sample_dir: Path) -> None:
        tool = DiscoverSourcesTool()
        result = await tool.execute({"path": str(sample_dir), "recursive": False}, ctx)
        assert not result.isError
        assert result.structuredContent is not None
        names = [item["name"] for item in result.structuredContent["items"]]
        assert "nested.pdf" not in names


# ---------------------------------------------------------------------------
# DescribeSourceTool
# ---------------------------------------------------------------------------


class TestDescribeSource:
    async def test_describe_file(self, ctx: KaosContext, sample_file: Path) -> None:
        tool = DescribeSourceTool()
        result = await tool.execute({"path": str(sample_file)}, ctx)
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["name"] == "hello.txt"
        assert result.structuredContent["size"] is not None
        assert result.structuredContent["size"] > 0

    async def test_describe_nonexistent(self, ctx: KaosContext) -> None:
        tool = DescribeSourceTool()
        result = await tool.execute({"path": "/nonexistent/file.txt"}, ctx)
        assert result.isError
        assert "not found" in (result.text or "").lower()

    async def test_describe_directory(self, ctx: KaosContext, sample_dir: Path) -> None:
        tool = DescribeSourceTool()
        result = await tool.execute({"path": str(sample_dir)}, ctx)
        assert result.isError
        assert "kaos-source-discover" in (result.text or "")

    async def test_describe_includes_mime_type(self, ctx: KaosContext, sample_file: Path) -> None:
        tool = DescribeSourceTool()
        result = await tool.execute({"path": str(sample_file)}, ctx)
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["mime_type"] is not None


# ---------------------------------------------------------------------------
# PreviewSourceTool
# ---------------------------------------------------------------------------


class TestPreviewSource:
    async def test_preview_text_file(self, ctx: KaosContext, sample_file: Path) -> None:
        tool = PreviewSourceTool()
        result = await tool.execute({"path": str(sample_file)}, ctx)
        assert not result.isError
        assert result.structuredContent is not None
        assert "text" in result.structuredContent
        assert "Hello" in result.structuredContent["text"]

    async def test_preview_with_max_bytes(self, ctx: KaosContext, sample_file: Path) -> None:
        tool = PreviewSourceTool()
        result = await tool.execute({"path": str(sample_file), "max_bytes": 5}, ctx)
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["truncated"] is True

    async def test_preview_binary_file(self, ctx: KaosContext, binary_file: Path) -> None:
        tool = PreviewSourceTool()
        result = await tool.execute({"path": str(binary_file)}, ctx)
        assert not result.isError
        assert result.structuredContent is not None
        assert "binary_base64" in result.structuredContent

    async def test_preview_nonexistent(self, ctx: KaosContext) -> None:
        tool = PreviewSourceTool()
        result = await tool.execute({"path": "/nonexistent/file.txt"}, ctx)
        assert result.isError
        assert "not found" in (result.text or "").lower()

    async def test_preview_directory(self, ctx: KaosContext, sample_dir: Path) -> None:
        tool = PreviewSourceTool()
        result = await tool.execute({"path": str(sample_dir)}, ctx)
        assert result.isError
        assert "kaos-source-discover" in (result.text or "")


# ---------------------------------------------------------------------------
# MaterializeSourceTool
# ---------------------------------------------------------------------------


class TestMaterializeSource:
    async def test_materialize_file(self, ctx: KaosContext, sample_file: Path) -> None:
        tool = MaterializeSourceTool()
        result = await tool.execute({"path": str(sample_file)}, ctx)
        assert not result.isError
        assert result.structuredContent is not None
        assert "artifact_id" in result.structuredContent

    async def test_materialize_with_name(self, ctx: KaosContext, sample_file: Path) -> None:
        tool = MaterializeSourceTool()
        result = await tool.execute({"path": str(sample_file), "name": "my-artifact"}, ctx)
        assert not result.isError

    async def test_materialize_nonexistent(self, ctx: KaosContext) -> None:
        tool = MaterializeSourceTool()
        result = await tool.execute({"path": "/nonexistent/file.txt"}, ctx)
        assert result.isError
        assert "not found" in (result.text or "").lower()

    async def test_materialize_directory(self, ctx: KaosContext, sample_dir: Path) -> None:
        tool = MaterializeSourceTool()
        result = await tool.execute({"path": str(sample_dir)}, ctx)
        assert result.isError
        assert "directory" in (result.text or "").lower()

    async def test_materialize_no_context(self, sample_file: Path) -> None:
        tool = MaterializeSourceTool()
        result = await tool.execute({"path": str(sample_file)}, context=None)
        assert result.isError
        assert "runtime" in (result.text or "").lower()


# ---------------------------------------------------------------------------
# FetchURLTool
# ---------------------------------------------------------------------------


class TestFetchURL:
    async def test_fetch_invalid_url(self, ctx: KaosContext) -> None:
        tool = FetchURLTool()
        result = await tool.execute({"url": "not-a-url"}, ctx)
        assert result.isError

    async def test_fetch_no_context(self) -> None:
        tool = FetchURLTool()
        result = await tool.execute({"url": "https://example.com"}, context=None)
        assert result.isError
        assert "runtime" in (result.text or "").lower()

    async def test_fetch_ftp_url(self, ctx: KaosContext) -> None:
        tool = FetchURLTool()
        result = await tool.execute({"url": "ftp://example.com/file"}, ctx)
        assert result.isError
        assert "http" in (result.text or "").lower()


# ---------------------------------------------------------------------------
# InspectArchiveTool
# ---------------------------------------------------------------------------


class TestInspectArchive:
    async def test_inspect_zip(self, ctx: KaosContext, sample_archive: Path) -> None:
        tool = InspectArchiveTool()
        result = await tool.execute({"path": str(sample_archive)}, ctx)
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["count"] >= 2
        names = [m["name"] for m in result.structuredContent["members"]]
        assert "doc.txt" in names

    async def test_inspect_with_pattern(self, ctx: KaosContext, sample_archive: Path) -> None:
        tool = InspectArchiveTool()
        result = await tool.execute({"path": str(sample_archive), "patterns": ["*.csv"]}, ctx)
        assert not result.isError
        assert result.structuredContent is not None
        names = [m["name"] for m in result.structuredContent["members"]]
        assert "report.csv" in names
        assert "doc.txt" not in names

    async def test_inspect_nonexistent(self, ctx: KaosContext) -> None:
        tool = InspectArchiveTool()
        result = await tool.execute({"path": "/nonexistent/test.zip"}, ctx)
        assert result.isError
        assert "not found" in (result.text or "").lower()

    async def test_inspect_directory(self, ctx: KaosContext, sample_dir: Path) -> None:
        tool = InspectArchiveTool()
        result = await tool.execute({"path": str(sample_dir)}, ctx)
        assert result.isError
        assert "kaos-source-discover" in (result.text or "")

    async def test_inspect_with_limit(self, ctx: KaosContext, sample_archive: Path) -> None:
        tool = InspectArchiveTool()
        result = await tool.execute({"path": str(sample_archive), "limit": 1}, ctx)
        assert not result.isError
        assert result.structuredContent is not None
        assert len(result.structuredContent["members"]) == 1


# ---------------------------------------------------------------------------
# Error message quality
# ---------------------------------------------------------------------------


class TestErrorMessages:
    """Verify error messages include recovery guidance."""

    async def test_discover_error_has_guidance(self, ctx: KaosContext) -> None:
        tool = DiscoverSourcesTool()
        result = await tool.execute({"path": "/nonexistent"}, ctx)
        assert result.isError
        text = result.text or ""
        assert "verify" in text.lower() or "path" in text.lower()

    async def test_describe_dir_suggests_discover(self, ctx: KaosContext, sample_dir: Path) -> None:
        tool = DescribeSourceTool()
        result = await tool.execute({"path": str(sample_dir)}, ctx)
        assert result.isError
        assert "kaos-source-discover" in (result.text or "")

    async def test_preview_dir_suggests_discover(self, ctx: KaosContext, sample_dir: Path) -> None:
        tool = PreviewSourceTool()
        result = await tool.execute({"path": str(sample_dir)}, ctx)
        assert result.isError
        assert "kaos-source-discover" in (result.text or "")

    async def test_materialize_no_ctx_suggests_preview(self, sample_file: Path) -> None:
        tool = MaterializeSourceTool()
        result = await tool.execute({"path": str(sample_file)}, context=None)
        assert result.isError
        assert "kaos-source-preview" in (result.text or "")

    async def test_fetch_url_error_suggests_browser(self, ctx: KaosContext) -> None:
        tool = FetchURLTool()
        # Use a URL that won't connect (localhost on unlikely port)
        result = await tool.execute({"url": "http://127.0.0.1:19999/test"}, ctx)
        assert result.isError
        text = result.text or ""
        assert "browser" in text.lower() or "kaos-web" in text.lower()
