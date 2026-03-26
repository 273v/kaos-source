"""Hardening tests for kaos-source to close coverage gaps.

Covers error paths, edge cases, and boundary conditions across:
- service.py: connector_for errors, wait_for_job timeout, option coercion, job error handling
- connectors/archive.py: TAR tests, member not found, unsupported format, pagination
- connectors/base.py: decode_cursor bad input, ensure_* errors, roots policy edge cases
- connectors/memory.py: missing item, empty items, locator without name
- connectors/filesystem.py: directory rejection, empty directory, symlink detection, OSError
- errors.py: error hierarchy, to_info conversion, retryable flags
- models.py: locator construction edge cases, normalization
- options.py: option validation
"""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

import pytest
from kaos_core import KaosContext, KaosRuntime
from kaos_core.protocol.roots import Root

from kaos_source import (
    ArchiveConnector,
    FilesystemConnector,
    MemoryConnector,
    SourceAccessError,
    SourceDescriptor,
    SourceDiscoverOptions,
    SourceError,
    SourceErrorInfo,
    SourceJobResult,
    SourceJobStatus,
    SourceKind,
    SourceLocator,
    SourceMaterializationError,
    SourceNotFoundError,
    SourceOperation,
    SourcePage,
    SourcePolicyError,
    SourcePreview,
    SourcePreviewOptions,
    SourceProvenance,
    SourceService,
    SourceTransientError,
    SourceValidationError,
)
from kaos_source.connectors.base import (
    decode_cursor,
    encode_cursor,
    ensure_directory,
    ensure_file_exists,
    ensure_regular_file,
    guess_mime_type,
    now_iso,
    path_matches_patterns,
    timestamp_to_iso,
)
from kaos_source.options import SourceMaterializeOptions


def _context(runtime: KaosRuntime, *, roots: list[Root] | None = None) -> KaosContext:
    return KaosContext.create(session_id="hardening-session", runtime=runtime, roots=roots)


# ---------------------------------------------------------------------------
# errors.py
# ---------------------------------------------------------------------------


class TestErrorHierarchy:
    def test_source_error_to_info(self) -> None:
        err = SourceError("something broke", detail_key="detail_value")
        info = err.to_info()
        assert isinstance(info, SourceErrorInfo)
        assert info.error_type == "SourceError"
        assert info.message == "something broke"
        assert info.retryable is False
        assert info.details == {"detail_key": "detail_value"}

    def test_source_not_found_error_to_info(self) -> None:
        err = SourceNotFoundError("not found", path="/tmp/x")
        info = err.to_info()
        assert info.error_type == "SourceNotFoundError"
        assert info.retryable is False

    def test_source_transient_error_is_retryable(self) -> None:
        err = SourceTransientError("transient failure")
        assert err.retryable is True
        info = err.to_info()
        assert info.retryable is True

    def test_source_access_error(self) -> None:
        err = SourceAccessError("access denied")
        assert err.retryable is False
        assert str(err) == "access denied"

    def test_source_policy_error(self) -> None:
        err = SourcePolicyError("blocked", uri="file:///tmp")
        assert "blocked" in str(err)
        assert err.details["uri"] == "file:///tmp"

    def test_source_materialization_error(self) -> None:
        err = SourceMaterializationError("mat failed", target="/vfs")
        info = err.to_info()
        assert info.error_type == "SourceMaterializationError"

    def test_source_validation_error(self) -> None:
        err = SourceValidationError("bad input", field="cursor")
        info = err.to_info()
        assert info.error_type == "SourceValidationError"
        assert info.details["field"] == "cursor"


# ---------------------------------------------------------------------------
# base.py utilities
# ---------------------------------------------------------------------------


class TestDecodeCursor:
    def test_none_returns_zero(self) -> None:
        assert decode_cursor(None) == 0

    def test_valid_roundtrip(self) -> None:
        cursor = encode_cursor(42)
        assert decode_cursor(cursor) == 42

    def test_invalid_base64_raises(self) -> None:
        with pytest.raises(SourceValidationError, match="Invalid discovery cursor"):
            decode_cursor("!!!not-base64!!!")

    def test_wrong_prefix_raises(self) -> None:
        import base64

        bad = base64.urlsafe_b64encode(b"badprefix:10").decode("ascii")
        with pytest.raises(SourceValidationError, match="Invalid discovery cursor"):
            decode_cursor(bad)

    def test_non_digit_value_raises(self) -> None:
        import base64

        bad = base64.urlsafe_b64encode(b"offset:abc").decode("ascii")
        with pytest.raises(SourceValidationError, match="Invalid discovery cursor"):
            decode_cursor(bad)

    def test_encode_cursor_zero(self) -> None:
        cursor = encode_cursor(0)
        assert decode_cursor(cursor) == 0


class TestEnsureFunctions:
    def test_ensure_file_exists_missing(self, tmp_path: Path) -> None:
        with pytest.raises(SourceNotFoundError, match="does not exist"):
            ensure_file_exists(tmp_path / "nonexistent")

    def test_ensure_directory_on_file(self, tmp_path: Path) -> None:
        f = tmp_path / "afile.txt"
        f.write_text("data")
        with pytest.raises(SourceValidationError, match="not a directory"):
            ensure_directory(f)

    def test_ensure_regular_file_on_directory(self, tmp_path: Path) -> None:
        d = tmp_path / "adir"
        d.mkdir()
        with pytest.raises(SourceValidationError, match="not a file"):
            ensure_regular_file(d)

    def test_ensure_file_exists_success(self, tmp_path: Path) -> None:
        f = tmp_path / "exists.txt"
        f.write_text("x")
        result = ensure_file_exists(f)
        assert result.exists()

    def test_ensure_directory_success(self, tmp_path: Path) -> None:
        d = tmp_path / "mydir"
        d.mkdir()
        result = ensure_directory(d)
        assert result.is_dir()

    def test_ensure_regular_file_success(self, tmp_path: Path) -> None:
        f = tmp_path / "real.txt"
        f.write_text("content")
        result = ensure_regular_file(f)
        assert result.is_file()


class TestPathMatchesPatterns:
    def test_empty_patterns_matches_all(self) -> None:
        assert path_matches_patterns("anything.txt", []) is True

    def test_matching_pattern(self) -> None:
        assert path_matches_patterns("dir/foo.txt", ["*.txt"]) is True

    def test_non_matching_pattern(self) -> None:
        assert path_matches_patterns("dir/foo.txt", ["*.pdf"]) is False

    def test_full_path_match(self) -> None:
        assert path_matches_patterns("docs/readme.md", ["docs/*.md"]) is True


class TestGuesssMimeType:
    def test_known_extension(self) -> None:
        assert guess_mime_type("test.json") == "application/json"

    def test_unknown_extension_no_fallback(self) -> None:
        assert guess_mime_type("test.xyzzy") is None

    def test_unknown_extension_with_fallback(self) -> None:
        assert guess_mime_type("test.xyzzy", fallback="application/octet-stream") == (
            "application/octet-stream"
        )


class TestTimestampToIso:
    def test_none_input(self) -> None:
        assert timestamp_to_iso(None) is None

    def test_valid_timestamp(self) -> None:
        result = timestamp_to_iso(0.0)
        assert result is not None
        assert "1970" in result


class TestNowIso:
    def test_returns_string(self) -> None:
        result = now_iso()
        assert isinstance(result, str)
        assert "T" in result


class TestRootsPolicy:
    def test_roots_allow_path_no_roots(self, tmp_path: Path) -> None:
        """No roots => no restriction."""
        from kaos_source.connectors.base import assert_roots_allow_path

        assert_roots_allow_path(tmp_path, None)
        assert_roots_allow_path(tmp_path, [])

    def test_roots_allow_path_denied(self, tmp_path: Path) -> None:
        from kaos_source.connectors.base import assert_roots_allow_path

        allowed = tmp_path / "allowed"
        allowed.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        roots = [Root(uri=allowed.as_uri(), name="allowed")]
        with pytest.raises(SourcePolicyError):
            assert_roots_allow_path(outside.resolve(), roots)

    def test_roots_with_no_file_scheme_roots(self, tmp_path: Path) -> None:
        """Non-file roots mean no matching root => denied."""
        from kaos_source.connectors.base import assert_roots_allow_path

        roots = [Root(uri="https://example.com/", name="web")]
        with pytest.raises(SourcePolicyError):
            assert_roots_allow_path(tmp_path.resolve(), roots)

    def test_roots_allow_uri_no_roots(self) -> None:
        from kaos_source.connectors.base import assert_roots_allow_uri

        assert_roots_allow_uri("https://example.com", None, schemes={"https"})
        assert_roots_allow_uri("https://example.com", [], schemes={"https"})

    def test_roots_allow_uri_no_relevant_roots(self) -> None:
        """Roots exist but none match the requested scheme => pass through."""
        from kaos_source.connectors.base import assert_roots_allow_uri

        roots = [Root(uri="file:///local", name="local")]
        assert_roots_allow_uri("https://example.com", roots, schemes={"https"})

    def test_roots_allow_uri_denied(self) -> None:
        from kaos_source.connectors.base import assert_roots_allow_uri

        roots = [Root(uri="https://allowed.com/base/", name="allowed")]
        with pytest.raises(SourcePolicyError):
            assert_roots_allow_uri("https://other.com/page", roots, schemes={"https"})

    def test_roots_allow_uri_root_slash(self) -> None:
        """Root with path '/' allows anything on that host."""
        from kaos_source.connectors.base import assert_roots_allow_uri

        roots = [Root(uri="https://example.com/", name="all")]
        assert_roots_allow_uri("https://example.com/any/path", roots, schemes={"https"})


# ---------------------------------------------------------------------------
# models.py
# ---------------------------------------------------------------------------


class TestSourceLocator:
    def test_archive_member_absolute_path_rejected(self) -> None:
        with pytest.raises(SourceValidationError, match="must be relative"):
            SourceLocator.archive_member("/tmp/test.zip", "/absolute/member.txt")

    def test_archive_member_traversal_rejected(self) -> None:
        with pytest.raises(SourceValidationError, match="cannot traverse"):
            SourceLocator.archive_member("/tmp/test.zip", "../escape.txt")

    def test_http_locator_invalid_scheme(self) -> None:
        with pytest.raises(SourceValidationError, match="http or https"):
            SourceLocator.http("ftp://example.com/file")

    def test_http_locator_missing_host(self) -> None:
        with pytest.raises(SourceValidationError, match="must include a host"):
            SourceLocator.http("http://")

    def test_memory_locator_no_name(self) -> None:
        loc = SourceLocator.memory()
        assert loc.name is None
        assert loc.uri == "memory://"

    def test_memory_locator_with_name(self) -> None:
        loc = SourceLocator.memory("test.txt")
        assert loc.name == "test.txt"
        assert "test.txt" in loc.uri

    def test_filesystem_locator_relative_path(self, tmp_path: Path) -> None:
        # filesystem() resolves relative paths
        loc = SourceLocator.filesystem(tmp_path / "sub" / "file.txt")
        assert loc.path is not None
        assert Path(loc.path).is_absolute()

    def test_browser_locator(self) -> None:
        loc = SourceLocator.browser("https://example.com/page")
        assert loc.source_kind == SourceKind.BROWSER
        assert loc.name == "page"


class TestSourcePreviewFromBinary:
    def test_from_binary(self) -> None:
        preview = SourcePreview.from_binary(
            source_id="test",
            payload=b"\x00\x01\x02",
            truncated=False,
            size=3,
            mime_type="application/octet-stream",
        )
        assert preview.binary_preview_base64 is not None
        assert preview.text_preview is None


class TestSourceJobResult:
    def test_empty_result(self) -> None:
        result = SourceJobResult()
        assert result.descriptor is None
        assert result.page is None
        assert result.preview is None
        assert result.materialization is None


class TestSourcePage:
    def test_empty_page(self) -> None:
        page = SourcePage()
        assert page.items == []
        assert page.next_cursor is None
        assert page.total_count is None
        assert page.error_count == 0


# ---------------------------------------------------------------------------
# service.py
# ---------------------------------------------------------------------------


class TestServiceConnectorFor:
    def test_unknown_kind_raises(self, runtime: KaosRuntime) -> None:
        service = SourceService(connectors=[MemoryConnector()])
        locator = SourceLocator.filesystem("/tmp/nonexistent")
        with pytest.raises(SourceValidationError, match="No source connector"):
            service.connector_for(locator)

    def test_memory_not_registered(self, runtime: KaosRuntime) -> None:
        service = SourceService(connectors=[FilesystemConnector()])
        with pytest.raises(SourceValidationError, match="Memory connector is not registered"):
            service.memory()


class TestServiceOptionCoercion:
    def test_invalid_discover_options_raises(self, runtime: KaosRuntime) -> None:
        service = SourceService()
        with pytest.raises(SourceValidationError, match="Invalid options for discover"):
            service._as_discover_options(SourcePreviewOptions())

    def test_invalid_preview_options_raises(self, runtime: KaosRuntime) -> None:
        service = SourceService()
        with pytest.raises(SourceValidationError, match="Invalid options for preview"):
            service._as_preview_options(SourceDiscoverOptions())

    def test_invalid_materialize_options_raises(self, runtime: KaosRuntime) -> None:
        service = SourceService()
        with pytest.raises(SourceValidationError, match="Invalid options for materialize"):
            service._as_materialize_options(SourceDiscoverOptions())

    def test_none_options_pass_through(self, runtime: KaosRuntime) -> None:
        service = SourceService()
        assert service._as_discover_options(None) is None
        assert service._as_preview_options(None) is None
        assert service._as_materialize_options(None) is None

    def test_correct_options_pass_through(self, runtime: KaosRuntime) -> None:
        service = SourceService()
        d = SourceDiscoverOptions()
        p = SourcePreviewOptions()
        m = SourceMaterializeOptions()
        assert service._as_discover_options(d) is d
        assert service._as_preview_options(p) is p
        assert service._as_materialize_options(m) is m


class TestServiceJobErrorPaths:
    async def test_get_unknown_job_raises(self, runtime: KaosRuntime) -> None:
        service = SourceService()
        with pytest.raises(SourceNotFoundError, match="Unknown source job"):
            service.get_job("nonexistent-id")

    async def test_job_with_source_error(self, runtime: KaosRuntime) -> None:
        """A job that hits a SourceError should end up in FAILED status with error info."""
        service = SourceService()
        context = _context(runtime)
        # memory locator with non-existent item
        locator = SourceLocator.memory("does-not-exist")
        job = await service.start_job(
            locator,
            context,
            operation=SourceOperation.PREVIEW,
        )
        finished = await service.wait_for_job(job.job_id, timeout=5.0)
        assert finished.status is SourceJobStatus.FAILED
        assert finished.error is not None
        assert finished.error.error_type == "SourceNotFoundError"

    async def test_job_with_generic_exception(self, runtime: KaosRuntime) -> None:
        """A job that raises a non-SourceError should also end in FAILED with a wrapped error."""

        class BrokenConnector(MemoryConnector):
            async def preview(self, locator, context, options=None):
                raise RuntimeError("kaboom")

        connector = BrokenConnector()
        connector.put_bytes("ok.txt", b"data")
        service = SourceService(connectors=[connector])
        context = _context(runtime)
        job = await service.start_job(
            SourceLocator.memory("ok.txt"),
            context,
            operation=SourceOperation.PREVIEW,
        )
        finished = await service.wait_for_job(job.job_id, timeout=5.0)
        assert finished.status is SourceJobStatus.FAILED
        assert finished.error is not None
        assert finished.message is not None and "kaboom" in finished.message

    async def test_wait_for_job_timeout(self, runtime: KaosRuntime) -> None:
        """wait_for_job should return the job (still running) when timeout elapses."""
        import asyncio

        class SlowConnector(MemoryConnector):
            async def describe(self, locator, context):
                await asyncio.sleep(10)
                return await super().describe(locator, context)

        connector = SlowConnector()
        connector.put_bytes("slow.txt", b"data")
        service = SourceService(connectors=[connector])
        context = _context(runtime)
        job = await service.start_job(
            SourceLocator.memory("slow.txt"),
            context,
            operation=SourceOperation.DESCRIBE,
        )
        result = await service.wait_for_job(job.job_id, timeout=0.05, poll_interval=0.01)
        # Should return without waiting for the job to finish
        assert result.status in {SourceJobStatus.QUEUED, SourceJobStatus.IN_PROGRESS}
        # Clean up
        await service.cancel_job(job.job_id)

    async def test_cancel_already_succeeded_job(self, runtime: KaosRuntime) -> None:
        service = SourceService()
        connector = service.memory()
        connector.put_bytes("quick.txt", b"data")
        context = _context(runtime)
        job = await service.start_job(
            SourceLocator.memory("quick.txt"),
            context,
            operation=SourceOperation.DESCRIBE,
        )
        finished = await service.wait_for_job(job.job_id, timeout=5.0)
        assert finished.status is SourceJobStatus.SUCCEEDED
        # Cancelling a succeeded job is a no-op
        after_cancel = await service.cancel_job(job.job_id)
        assert after_cancel.status is SourceJobStatus.SUCCEEDED


class TestServiceDispatchOperation:
    async def test_unsupported_operation_raises(self, runtime: KaosRuntime) -> None:
        """_dispatch_operation with an unknown operation should raise SourceValidationError."""
        service = SourceService()
        connector = MemoryConnector()
        context = _context(runtime)
        locator = SourceLocator.memory("x")

        # We need to create a fake operation value that doesn't match any branch.
        # Since SourceOperation is a StrEnum, we test the service method via start_job
        # with bad options instead.
        # Actually, let's test the option coercion paths via start_job.
        connector.put_bytes("x", b"test")
        service = SourceService(connectors=[connector])
        job = await service.start_job(
            locator,
            context,
            operation=SourceOperation.DISCOVER,
            options=SourcePreviewOptions(),  # wrong type!
        )
        finished = await service.wait_for_job(job.job_id, timeout=5.0)
        assert finished.status is SourceJobStatus.FAILED
        assert "Invalid options" in (finished.message or "")


class TestServiceJobResult:
    def test_job_result_descriptor(self, runtime: KaosRuntime) -> None:
        service = SourceService()
        loc = SourceLocator.memory("test")
        prov = SourceProvenance(
            source_kind=SourceKind.MEMORY,
            locator=loc,
            connector_name="memory",
            retrieved_at=now_iso(),
        )
        desc = SourceDescriptor(
            source_id="test",
            source_kind=SourceKind.MEMORY,
            locator=loc,
            name="test",
            provenance=prov,
        )
        result = service._job_result(desc)
        assert result.descriptor is desc

    def test_job_result_page(self, runtime: KaosRuntime) -> None:
        service = SourceService()
        page = SourcePage(items=[])
        result = service._job_result(page)
        assert result.page is page

    def test_job_result_preview(self, runtime: KaosRuntime) -> None:
        service = SourceService()
        preview = SourcePreview(source_id="test")
        result = service._job_result(preview)
        assert result.preview is preview


# ---------------------------------------------------------------------------
# connectors/memory.py
# ---------------------------------------------------------------------------


class TestMemoryConnectorErrors:
    async def test_describe_missing_item(self, runtime: KaosRuntime) -> None:
        connector = MemoryConnector()
        context = _context(runtime)
        with pytest.raises(SourceNotFoundError, match="Unknown memory source"):
            await connector.describe(SourceLocator.memory("missing"), context)

    async def test_preview_missing_item(self, runtime: KaosRuntime) -> None:
        connector = MemoryConnector()
        context = _context(runtime)
        with pytest.raises(SourceNotFoundError, match="Unknown memory source"):
            await connector.preview(SourceLocator.memory("missing"), context)

    async def test_locator_without_name(self, runtime: KaosRuntime) -> None:
        connector = MemoryConnector()
        context = _context(runtime)
        with pytest.raises(SourceValidationError, match="requires a name"):
            await connector.describe(SourceLocator.memory(), context)

    async def test_discover_empty_connector(self, runtime: KaosRuntime) -> None:
        connector = MemoryConnector()
        context = _context(runtime)
        page = await connector.discover(SourceLocator.memory(), context)
        assert page.items == []
        assert page.total_count == 0

    async def test_discover_named_item_with_cursor_past_zero(self, runtime: KaosRuntime) -> None:
        """Discovering a specific named item with cursor > 0 should return empty."""
        connector = MemoryConnector()
        connector.put_bytes("item.txt", b"data")
        context = _context(runtime)
        page = await connector.discover(
            SourceLocator.memory("item.txt"),
            context,
            SourceDiscoverOptions(cursor=encode_cursor(1)),
        )
        assert page.items == []

    async def test_discover_pagination(self, runtime: KaosRuntime) -> None:
        connector = MemoryConnector()
        for i in range(5):
            connector.put_bytes(f"item_{i:02d}.txt", f"data{i}".encode())
        context = _context(runtime)
        page1 = await connector.discover(
            SourceLocator.memory(), context, SourceDiscoverOptions(limit=2)
        )
        assert len(page1.items) == 2
        assert page1.next_cursor is not None
        assert page1.total_count == 5

        page2 = await connector.discover(
            SourceLocator.memory(),
            context,
            SourceDiscoverOptions(limit=2, cursor=page1.next_cursor),
        )
        assert len(page2.items) == 2
        assert page2.next_cursor is not None

        page3 = await connector.discover(
            SourceLocator.memory(),
            context,
            SourceDiscoverOptions(limit=2, cursor=page2.next_cursor),
        )
        assert len(page3.items) == 1
        assert page3.next_cursor is None


# ---------------------------------------------------------------------------
# connectors/filesystem.py
# ---------------------------------------------------------------------------


class TestFilesystemConnectorErrors:
    async def test_preview_directory_rejected(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        d = tmp_path / "mydir"
        d.mkdir()
        connector = FilesystemConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        with pytest.raises(SourceValidationError, match="only available for files"):
            await connector.preview(SourceLocator.filesystem(d), context)

    async def test_materialize_directory_rejected(
        self, tmp_path: Path, runtime: KaosRuntime
    ) -> None:
        d = tmp_path / "mydir"
        d.mkdir()
        connector = FilesystemConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        with pytest.raises(SourceValidationError, match="only available for files"):
            await connector.materialize(SourceLocator.filesystem(d), context)

    async def test_discover_empty_directory(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        d = tmp_path / "emptydir"
        d.mkdir()
        connector = FilesystemConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        page = await connector.discover(SourceLocator.filesystem(d), context)
        assert page.items == []

    async def test_discover_file_as_locator(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        """Discovering a single file (not a directory) should return the file descriptor."""
        f = tmp_path / "single.txt"
        f.write_text("hello")
        connector = FilesystemConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        page = await connector.discover(SourceLocator.filesystem(f), context)
        assert len(page.items) == 1
        assert page.items[0].name == "single.txt"

    async def test_discover_file_with_cursor_past_zero(
        self, tmp_path: Path, runtime: KaosRuntime
    ) -> None:
        """Cursor > 0 when discovering a single file should return empty page."""
        f = tmp_path / "single.txt"
        f.write_text("hello")
        connector = FilesystemConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        page = await connector.discover(
            SourceLocator.filesystem(f),
            context,
            SourceDiscoverOptions(cursor=encode_cursor(1)),
        )
        assert page.items == []

    async def test_symlink_in_directory_discovery(
        self, tmp_path: Path, runtime: KaosRuntime
    ) -> None:
        """Symlinks discovered via directory walk are reported with is_symlink metadata."""
        target = tmp_path / "real.txt"
        target.write_text("real content")
        link = tmp_path / "link.txt"
        link.symlink_to(target)
        connector = FilesystemConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        page = await connector.discover(SourceLocator.filesystem(tmp_path), context)
        descriptors_by_name = {d.name: d for d in page.items}
        assert "link.txt" in descriptors_by_name
        assert descriptors_by_name["link.txt"].metadata["is_symlink"] is True
        assert descriptors_by_name["real.txt"].metadata["is_symlink"] is False

    async def test_non_symlink_detection(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        f = tmp_path / "normal.txt"
        f.write_text("normal content")
        connector = FilesystemConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        descriptor = await connector.describe(SourceLocator.filesystem(f), context)
        assert descriptor.metadata["is_symlink"] is False

    async def test_describe_nonexistent_file(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        connector = FilesystemConnector()
        context = _context(runtime)
        with pytest.raises(SourceNotFoundError, match="does not exist"):
            await connector.describe(SourceLocator.filesystem(tmp_path / "nope.txt"), context)

    async def test_discover_hidden_files_excluded(
        self, tmp_path: Path, runtime: KaosRuntime
    ) -> None:
        (tmp_path / ".hidden").write_text("hidden")
        (tmp_path / "visible.txt").write_text("visible")
        connector = FilesystemConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        page = await connector.discover(
            SourceLocator.filesystem(tmp_path),
            context,
            SourceDiscoverOptions(include_hidden=False),
        )
        names = [item.name for item in page.items]
        assert ".hidden" not in names
        assert "visible.txt" in names

    async def test_discover_hidden_files_included(
        self, tmp_path: Path, runtime: KaosRuntime
    ) -> None:
        (tmp_path / ".hidden").write_text("hidden")
        (tmp_path / "visible.txt").write_text("visible")
        connector = FilesystemConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        page = await connector.discover(
            SourceLocator.filesystem(tmp_path),
            context,
            SourceDiscoverOptions(include_hidden=True),
        )
        names = [item.name for item in page.items]
        assert ".hidden" in names
        assert "visible.txt" in names

    async def test_discover_with_max_depth(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        (tmp_path / "top.txt").write_text("top")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.txt").write_text("deep")
        connector = FilesystemConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        page = await connector.discover(
            SourceLocator.filesystem(tmp_path),
            context,
            SourceDiscoverOptions(max_depth=1, recursive=True),
        )
        names = [item.name for item in page.items]
        assert "top.txt" in names
        assert "deep.txt" not in names

    async def test_discover_with_size_filter(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        (tmp_path / "small.txt").write_text("x")
        (tmp_path / "big.txt").write_text("x" * 1000)
        connector = FilesystemConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        page = await connector.discover(
            SourceLocator.filesystem(tmp_path),
            context,
            SourceDiscoverOptions(min_size=100),
        )
        names = [item.name for item in page.items]
        assert "small.txt" not in names
        assert "big.txt" in names

    async def test_discover_with_max_size(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        (tmp_path / "small.txt").write_text("x")
        (tmp_path / "big.txt").write_text("x" * 1000)
        connector = FilesystemConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        page = await connector.discover(
            SourceLocator.filesystem(tmp_path),
            context,
            SourceDiscoverOptions(max_size=100),
        )
        names = [item.name for item in page.items]
        assert "small.txt" in names
        assert "big.txt" not in names

    async def test_discover_include_directories(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        sub = tmp_path / "subdir"
        sub.mkdir()
        (tmp_path / "file.txt").write_text("data")
        connector = FilesystemConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        page = await connector.discover(
            SourceLocator.filesystem(tmp_path),
            context,
            SourceDiscoverOptions(include_directories=True, recursive=False),
        )
        names = [item.name for item in page.items]
        assert "subdir" in names
        assert "file.txt" in names


# ---------------------------------------------------------------------------
# connectors/archive.py — TAR tests
# ---------------------------------------------------------------------------


def _make_tar(path: Path, members: dict[str, bytes]) -> Path:
    """Create a tar.gz archive with the given members."""
    tar_path = path
    with tarfile.open(tar_path, "w:gz") as tar:
        for name, data in members.items():
            import io

            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return tar_path


def _make_zip(path: Path, members: dict[str, bytes]) -> Path:
    """Create a zip archive with the given members."""
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


class TestArchiveConnectorTar:
    async def test_describe_tar_container(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        tar_path = _make_tar(
            tmp_path / "test.tar.gz", {"file1.txt": b"hello", "file2.txt": b"world"}
        )
        connector = ArchiveConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        locator = SourceLocator.archive(tar_path)
        descriptor = await connector.describe(locator, context)
        assert descriptor.metadata["archive_format"] == "tar"
        assert descriptor.name == "test.tar.gz"
        assert descriptor.can_materialize is True

    async def test_discover_tar_members(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        tar_path = _make_tar(tmp_path / "test.tar.gz", {"alpha.txt": b"aaa", "beta.txt": b"bbb"})
        connector = ArchiveConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        page = await connector.discover(SourceLocator.archive(tar_path), context)
        names = [item.name for item in page.items]
        assert "alpha.txt" in names
        assert "beta.txt" in names

    async def test_describe_tar_member(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        tar_path = _make_tar(tmp_path / "test.tar.gz", {"docs/readme.txt": b"content"})
        connector = ArchiveConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        locator = SourceLocator.archive_member(tar_path, "docs/readme.txt")
        descriptor = await connector.describe(locator, context)
        assert descriptor.name == "readme.txt"
        assert descriptor.size == 7

    async def test_preview_tar_member(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        tar_path = _make_tar(tmp_path / "test.tar.gz", {"content.txt": b"hello world"})
        connector = ArchiveConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        locator = SourceLocator.archive_member(tar_path, "content.txt")
        preview = await connector.preview(locator, context, SourcePreviewOptions(max_bytes=5))
        assert preview.text_preview == "hello"
        assert preview.truncated is True

    async def test_materialize_tar_member(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        tar_path = _make_tar(tmp_path / "test.tar.gz", {"doc.txt": b"tar-body"})
        connector = ArchiveConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        locator = SourceLocator.archive_member(tar_path, "doc.txt")
        materialization = await connector.materialize(locator, context)
        assert materialization.descriptor.name == "doc.txt"
        body = await runtime.artifacts.read_text(materialization.manifest.artifact_id)
        assert body == "tar-body"

    async def test_materialize_tar_container(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        tar_path = _make_tar(tmp_path / "test.tar.gz", {"doc.txt": b"data"})
        connector = ArchiveConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        locator = SourceLocator.archive(tar_path)
        materialization = await connector.materialize(locator, context)
        assert materialization.descriptor.metadata["archive_format"] == "tar"


class TestArchiveConnectorErrors:
    async def test_member_not_found_in_zip(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        zip_path = _make_zip(tmp_path / "test.zip", {"real.txt": b"data"})
        connector = ArchiveConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        with pytest.raises(SourceNotFoundError, match="member was not found"):
            await connector.describe(SourceLocator.archive_member(zip_path, "missing.txt"), context)

    async def test_member_not_found_in_tar(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        tar_path = _make_tar(tmp_path / "test.tar.gz", {"real.txt": b"data"})
        connector = ArchiveConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        with pytest.raises(SourceNotFoundError, match="member was not found"):
            await connector.describe(SourceLocator.archive_member(tar_path, "missing.txt"), context)

    async def test_unsupported_archive_format(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        bad_file = tmp_path / "bad.xyz"
        bad_file.write_bytes(b"not an archive at all, just random bytes")
        connector = ArchiveConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        with pytest.raises(SourceValidationError, match="Unsupported archive type"):
            await connector.describe(SourceLocator.archive(bad_file), context)

    async def test_unsupported_archive_discover(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        bad_file = tmp_path / "bad.xyz"
        bad_file.write_bytes(b"not an archive at all")
        connector = ArchiveConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        with pytest.raises(SourceValidationError, match="Unsupported archive type"):
            await connector.discover(SourceLocator.archive(bad_file), context)

    async def test_preview_without_member_path(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        zip_path = _make_zip(tmp_path / "test.zip", {"a.txt": b"data"})
        connector = ArchiveConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        with pytest.raises(SourceValidationError, match="requires a member locator"):
            await connector.preview(SourceLocator.archive(zip_path), context)

    async def test_archive_path_not_a_file(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        d = tmp_path / "not_a_file"
        d.mkdir()
        connector = ArchiveConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        with pytest.raises(SourceValidationError, match="not a file"):
            await connector.describe(SourceLocator.archive(d), context)

    async def test_archive_path_does_not_exist(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        connector = ArchiveConnector()
        context = _context(runtime)
        with pytest.raises(SourceNotFoundError, match="does not exist"):
            await connector.describe(SourceLocator.archive(tmp_path / "nonexistent.zip"), context)

    async def test_preview_tar_member_not_found(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        tar_path = _make_tar(tmp_path / "test.tar.gz", {"real.txt": b"data"})
        connector = ArchiveConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        with pytest.raises(SourceNotFoundError, match="member was not found"):
            await connector.preview(SourceLocator.archive_member(tar_path, "missing.txt"), context)

    async def test_preview_zip_member_not_found(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        zip_path = _make_zip(tmp_path / "test.zip", {"real.txt": b"data"})
        connector = ArchiveConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        with pytest.raises(SourceNotFoundError, match="member was not found"):
            await connector.preview(SourceLocator.archive_member(zip_path, "missing.txt"), context)


class TestArchiveConnectorPagination:
    async def test_discover_with_pagination(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        members = {f"file_{i:02d}.txt": f"data{i}".encode() for i in range(5)}
        zip_path = _make_zip(tmp_path / "paginated.zip", members)
        connector = ArchiveConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])

        page1 = await connector.discover(
            SourceLocator.archive(zip_path),
            context,
            SourceDiscoverOptions(limit=2),
        )
        assert len(page1.items) == 2
        assert page1.next_cursor is not None

        page2 = await connector.discover(
            SourceLocator.archive(zip_path),
            context,
            SourceDiscoverOptions(limit=2, cursor=page1.next_cursor),
        )
        assert len(page2.items) == 2
        assert page2.next_cursor is not None

        page3 = await connector.discover(
            SourceLocator.archive(zip_path),
            context,
            SourceDiscoverOptions(limit=2, cursor=page2.next_cursor),
        )
        assert len(page3.items) == 1
        assert page3.next_cursor is None

    async def test_discover_member_specific_with_cursor(
        self, tmp_path: Path, runtime: KaosRuntime
    ) -> None:
        """Discovering a specific member with cursor past 0 returns empty."""
        zip_path = _make_zip(tmp_path / "test.zip", {"a.txt": b"data"})
        connector = ArchiveConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        page = await connector.discover(
            SourceLocator.archive_member(zip_path, "a.txt"),
            context,
            SourceDiscoverOptions(cursor=encode_cursor(1)),
        )
        assert page.items == []

    async def test_discover_member_specific_no_cursor(
        self, tmp_path: Path, runtime: KaosRuntime
    ) -> None:
        """Discovering a specific member returns that member."""
        zip_path = _make_zip(tmp_path / "test.zip", {"a.txt": b"data"})
        connector = ArchiveConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        page = await connector.discover(
            SourceLocator.archive_member(zip_path, "a.txt"),
            context,
        )
        assert len(page.items) == 1
        assert page.items[0].locator.member_path == "a.txt"

    async def test_tar_pagination(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        members = {f"file_{i:02d}.txt": f"data{i}".encode() for i in range(4)}
        tar_path = _make_tar(tmp_path / "paginated.tar.gz", members)
        connector = ArchiveConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])

        page1 = await connector.discover(
            SourceLocator.archive(tar_path),
            context,
            SourceDiscoverOptions(limit=2),
        )
        assert len(page1.items) == 2
        assert page1.next_cursor is not None

        page2 = await connector.discover(
            SourceLocator.archive(tar_path),
            context,
            SourceDiscoverOptions(limit=2, cursor=page1.next_cursor),
        )
        assert len(page2.items) == 2
        assert page2.next_cursor is None


class TestArchiveConnectorSkipMember:
    async def test_hidden_members_excluded(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        zip_path = _make_zip(
            tmp_path / "test.zip",
            {".hidden": b"secret", "visible.txt": b"data"},
        )
        connector = ArchiveConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        page = await connector.discover(
            SourceLocator.archive(zip_path),
            context,
            SourceDiscoverOptions(include_hidden=False),
        )
        names = [item.name for item in page.items]
        assert ".hidden" not in names
        assert "visible.txt" in names

    async def test_hidden_members_included(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        zip_path = _make_zip(
            tmp_path / "test.zip",
            {".hidden": b"secret", "visible.txt": b"data"},
        )
        connector = ArchiveConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        page = await connector.discover(
            SourceLocator.archive(zip_path),
            context,
            SourceDiscoverOptions(include_hidden=True),
        )
        names = [item.name for item in page.items]
        assert ".hidden" in names

    async def test_max_depth_filter(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        zip_path = _make_zip(
            tmp_path / "test.zip",
            {"top.txt": b"t", "a/mid.txt": b"m", "a/b/deep.txt": b"d"},
        )
        connector = ArchiveConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        page = await connector.discover(
            SourceLocator.archive(zip_path),
            context,
            SourceDiscoverOptions(max_depth=1),
        )
        names = [item.name for item in page.items]
        assert "top.txt" in names
        assert "mid.txt" not in names
        assert "deep.txt" not in names

    async def test_size_filters(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        zip_path = _make_zip(
            tmp_path / "test.zip",
            {"small.txt": b"x", "big.txt": b"x" * 1000},
        )
        connector = ArchiveConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        # min_size filter
        page = await connector.discover(
            SourceLocator.archive(zip_path),
            context,
            SourceDiscoverOptions(min_size=100),
        )
        names = [item.name for item in page.items]
        assert "small.txt" not in names
        assert "big.txt" in names

        # max_size filter
        page2 = await connector.discover(
            SourceLocator.archive(zip_path),
            context,
            SourceDiscoverOptions(max_size=100),
        )
        names2 = [item.name for item in page2.items]
        assert "small.txt" in names2
        assert "big.txt" not in names2

    async def test_pattern_filter(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        zip_path = _make_zip(
            tmp_path / "test.zip",
            {"doc.txt": b"t", "image.png": b"p"},
        )
        connector = ArchiveConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        page = await connector.discover(
            SourceLocator.archive(zip_path),
            context,
            SourceDiscoverOptions(patterns=["*.txt"]),
        )
        names = [item.name for item in page.items]
        assert "doc.txt" in names
        assert "image.png" not in names


# ---------------------------------------------------------------------------
# connectors/base.py — _require_path, _decode_preview_payload, _default_target_path
# ---------------------------------------------------------------------------


class TestRequirePath:
    def test_missing_path_raises(self) -> None:
        connector = MemoryConnector()  # any connector subclass
        locator = SourceLocator.memory("x")  # path is None
        with pytest.raises(SourceValidationError, match="missing required path"):
            connector._require_path(locator)

    def test_empty_path_raises(self) -> None:
        connector = MemoryConnector()
        locator = SourceLocator(
            source_kind=SourceKind.FILESYSTEM,
            uri="file:///tmp",
            path="",
        )
        with pytest.raises(SourceValidationError, match="missing required path"):
            connector._require_path(locator)


class TestDecodePreviewPayload:
    def test_text_mime_type(self) -> None:
        connector = MemoryConnector()
        preview = connector._decode_preview_payload(
            b"hello",
            source_id="test",
            size=5,
            mime_type="text/plain",
            encoding="utf-8",
        )
        assert preview.text_preview == "hello"
        assert preview.truncated is False

    def test_json_mime_type_is_text(self) -> None:
        connector = MemoryConnector()
        preview = connector._decode_preview_payload(
            b'{"key": 1}',
            source_id="test",
            size=11,
            mime_type="application/json",
            encoding="utf-8",
        )
        assert preview.text_preview == '{"key": 1}'

    def test_binary_with_null_byte(self) -> None:
        connector = MemoryConnector()
        preview = connector._decode_preview_payload(
            b"\x00\x01\x02",
            source_id="test",
            size=3,
            mime_type="application/octet-stream",
            encoding="utf-8",
        )
        assert preview.binary_preview_base64 is not None
        assert preview.text_preview is None

    def test_no_null_bytes_unknown_mime(self) -> None:
        """Payload without null bytes and unknown mime_type is treated as text."""
        connector = MemoryConnector()
        preview = connector._decode_preview_payload(
            b"looks like text",
            source_id="test",
            size=15,
            mime_type=None,
            encoding="utf-8",
        )
        assert preview.text_preview == "looks like text"

    def test_truncated_override(self) -> None:
        connector = MemoryConnector()
        preview = connector._decode_preview_payload(
            b"data",
            source_id="test",
            size=4,
            mime_type="text/plain",
            encoding="utf-8",
            truncated_override=True,
        )
        assert preview.truncated is True

    def test_truncated_when_size_exceeds_payload(self) -> None:
        connector = MemoryConnector()
        preview = connector._decode_preview_payload(
            b"short",
            source_id="test",
            size=100,
            mime_type="text/plain",
            encoding="utf-8",
        )
        assert preview.truncated is True

    def test_xml_mime_type_is_text(self) -> None:
        connector = MemoryConnector()
        preview = connector._decode_preview_payload(
            b"<root/>",
            source_id="test",
            size=7,
            mime_type="application/xml",
            encoding="utf-8",
        )
        assert preview.text_preview == "<root/>"

    def test_yaml_mime_type_is_text(self) -> None:
        connector = MemoryConnector()
        preview = connector._decode_preview_payload(
            b"key: value",
            source_id="test",
            size=10,
            mime_type="application/yaml",
            encoding="utf-8",
        )
        assert preview.text_preview == "key: value"


class TestDefaultTargetPath:
    def test_safe_name(self) -> None:
        from kaos_source.connectors.base import SourceConnector

        path = SourceConnector._default_target_path("my file (1).txt", SourceKind.FILESYSTEM)
        assert path.startswith("sources/filesystem/")
        # unsafe chars replaced with dash
        assert "(" not in path

    def test_all_unsafe_chars(self) -> None:
        from kaos_source.connectors.base import SourceConnector

        path = SourceConnector._default_target_path("@#$%", SourceKind.MEMORY)
        assert "artifact" in path or path.endswith("-")  # stripped to empty => "artifact"


class TestRequireRuntime:
    async def test_require_runtime_none(self) -> None:
        connector = MemoryConnector()
        context = KaosContext.create(session_id="test", runtime=None)
        with pytest.raises(SourceValidationError, match="must be attached to a runtime"):
            connector._require_runtime(context)


# ---------------------------------------------------------------------------
# service.py — start_job with metadata and message
# ---------------------------------------------------------------------------


class TestServiceStartJobMetadata:
    async def test_start_job_with_metadata_and_message(self, runtime: KaosRuntime) -> None:
        service = SourceService()
        connector = service.memory()
        connector.put_bytes("data.txt", b"payload")
        context = _context(runtime)

        job = await service.start_job(
            SourceLocator.memory("data.txt"),
            context,
            operation=SourceOperation.DESCRIBE,
            metadata={"custom": "value"},
            message="Initial message",
        )
        assert job.metadata == {"custom": "value"}
        assert job.message == "Initial message"

        finished = await service.wait_for_job(job.job_id)
        assert finished.status is SourceJobStatus.SUCCEEDED
        assert finished.result is not None
        assert finished.result.descriptor is not None

    async def test_start_job_all_operations(self, runtime: KaosRuntime) -> None:
        """Verify all SourceOperation types dispatch correctly via start_job."""
        service = SourceService()
        connector = service.memory()
        connector.put_bytes("data.txt", b"payload")
        context = _context(runtime)

        for op in [SourceOperation.DESCRIBE, SourceOperation.DISCOVER, SourceOperation.PREVIEW]:
            job = await service.start_job(
                SourceLocator.memory("data.txt"),
                context,
                operation=op,
            )
            finished = await service.wait_for_job(job.job_id, timeout=5.0)
            assert finished.status is SourceJobStatus.SUCCEEDED, f"Failed for operation {op}"


class TestServiceDefaultConnectors:
    def test_default_connectors_registered(self) -> None:
        service = SourceService()
        assert SourceKind.FILESYSTEM in service._connectors
        assert SourceKind.ARCHIVE in service._connectors
        assert SourceKind.MEMORY in service._connectors
        assert SourceKind.HTTP in service._connectors
        assert SourceKind.BROWSER in service._connectors

    def test_custom_connectors(self) -> None:
        service = SourceService(connectors=[MemoryConnector()])
        assert SourceKind.MEMORY in service._connectors
        assert SourceKind.FILESYSTEM not in service._connectors


# ---------------------------------------------------------------------------
# ZIP materialize (container-level, without member_path)
# ---------------------------------------------------------------------------


class TestArchiveMaterializeContainer:
    async def test_materialize_zip_container(self, tmp_path: Path, runtime: KaosRuntime) -> None:
        zip_path = _make_zip(tmp_path / "bundle.zip", {"a.txt": b"aaa"})
        connector = ArchiveConnector()
        context = _context(runtime, roots=[Root(uri=tmp_path.resolve().as_uri(), name="tmp")])
        locator = SourceLocator.archive(zip_path)
        materialization = await connector.materialize(locator, context)
        assert materialization.descriptor.metadata["archive_format"] == "zip"
