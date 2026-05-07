from __future__ import annotations

import asyncio
import contextlib
import tarfile
import zipfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import cast

from kaos_core import KaosContext
from kaos_core.logging import get_logger

from kaos_source.connectors.base import (
    Closable,
    ReadableBinaryStream,
    SourceConnector,
    assert_roots_allow_path,
    decode_cursor,
    encode_cursor,
    ensure_regular_file,
    guess_mime_type,
    path_matches_patterns,
    timestamp_to_iso,
)
from kaos_source.errors import SourceAccessError, SourceNotFoundError, SourceValidationError
from kaos_source.models import (
    SourceDescriptor,
    SourceKind,
    SourceLocator,
    SourceMaterialization,
    SourcePage,
    SourcePreview,
)
from kaos_source.options import (
    SourceDiscoverOptions,
    SourceMaterializeOptions,
    SourcePreviewOptions,
)

logger = get_logger(__name__)


class ArchiveConnector(SourceConnector):
    kind = SourceKind.ARCHIVE
    name = "archive"

    async def describe(self, locator: SourceLocator, context: KaosContext) -> SourceDescriptor:
        archive_path = Path(self._require_path(locator, field="archive_path"))
        resolved = await asyncio.to_thread(ensure_regular_file, archive_path)
        assert_roots_allow_path(resolved, context.roots)
        logger.debug("Describing archive %s (member=%s)", resolved, locator.member_path)

        if locator.member_path is None:
            stat = await asyncio.to_thread(resolved.stat)
            container_locator = SourceLocator.archive(resolved)
            return SourceDescriptor(
                source_id=container_locator.uri,
                source_kind=self.kind,
                locator=container_locator,
                name=resolved.name,
                mime_type=guess_mime_type(resolved.name, fallback="application/octet-stream"),
                size=stat.st_size,
                created_at=timestamp_to_iso(stat.st_ctime),
                modified_at=timestamp_to_iso(stat.st_mtime),
                metadata={
                    "kind": "archive",
                    "archive_format": await asyncio.to_thread(self._archive_format, resolved),
                    "path": str(resolved),
                },
                provenance=self._provenance(
                    container_locator, request_metadata={"resolved_path": str(resolved)}
                ),
                can_materialize=True,
                preview_available=False,
            )

        return await asyncio.to_thread(self._describe_member, resolved, locator.member_path)

    async def discover(
        self,
        locator: SourceLocator,
        context: KaosContext,
        options: SourceDiscoverOptions | None = None,
    ) -> SourcePage:
        options = options or SourceDiscoverOptions()
        archive_path = Path(self._require_path(locator, field="archive_path"))
        resolved = await asyncio.to_thread(ensure_regular_file, archive_path)
        assert_roots_allow_path(resolved, context.roots)

        if locator.member_path is not None:
            if decode_cursor(options.cursor) > 0:
                return SourcePage(items=[])
            return SourcePage(items=[await self.describe(locator, context)])

        start_offset = decode_cursor(options.cursor)
        logger.debug("Discovering members in archive %s (limit=%d)", resolved, options.limit)
        items, next_cursor = await asyncio.to_thread(
            self._discover_members_page,
            resolved,
            options,
            start_offset,
        )
        logger.debug("Discovered %d members in %s", len(items), resolved)
        return SourcePage(items=items, next_cursor=next_cursor)

    async def preview(
        self,
        locator: SourceLocator,
        context: KaosContext,
        options: SourcePreviewOptions | None = None,
    ) -> SourcePreview:
        options = options or SourcePreviewOptions()
        if locator.member_path is None:
            raise SourceValidationError(
                "Archive preview requires a member locator", locator=locator.uri
            )
        descriptor = await self.describe(locator, context)
        archive_path = Path(self._require_path(locator, field="archive_path"))
        resolved = await asyncio.to_thread(ensure_regular_file, archive_path)
        payload = await asyncio.to_thread(
            self._read_member_preview, resolved, locator.member_path, options.max_bytes
        )
        return self._decode_preview_payload(
            payload,
            source_id=descriptor.source_id,
            size=descriptor.size,
            mime_type=descriptor.mime_type,
            encoding=options.encoding,
        )

    async def materialize(
        self,
        locator: SourceLocator,
        context: KaosContext,
        options: SourceMaterializeOptions | None = None,
    ) -> SourceMaterialization:
        options = options or SourceMaterializeOptions()
        descriptor = await self.describe(locator, context)
        archive_path = Path(self._require_path(locator, field="archive_path"))
        resolved = await asyncio.to_thread(ensure_regular_file, archive_path)
        logger.debug("Materializing archive %s (member=%s)", resolved, locator.member_path)
        if locator.member_path is None:
            return await self._materialize_local_path(
                source_path=resolved,
                context=context,
                descriptor=descriptor,
                options=options,
            )
        member_path = locator.member_path
        return await self._materialize_stream(
            stream_factory=lambda: self._open_member_stream(resolved, member_path),
            context=context,
            descriptor=descriptor,
            options=options,
        )

    def _discover_members_page(
        self,
        archive_path: Path,
        options: SourceDiscoverOptions,
        start_offset: int,
    ) -> tuple[list[SourceDescriptor], str | None]:
        items: list[SourceDescriptor] = []
        matched = 0
        next_cursor: str | None = None
        for descriptor in self._iter_members(archive_path, options):
            if matched < start_offset:
                matched += 1
                continue
            if len(items) >= options.limit:
                next_cursor = encode_cursor(matched)
                break
            items.append(descriptor)
            matched += 1
        return items, next_cursor

    def _iter_members(
        self,
        archive_path: Path,
        options: SourceDiscoverOptions,
    ) -> list[SourceDescriptor]:
        entries: list[SourceDescriptor] = []
        # KSRC-03: running totals for the cumulative uncompressed cap and
        # the per-member decompression-ratio check.
        total_uncompressed = 0
        max_total = options.max_total_uncompressed
        max_ratio = options.max_decompression_ratio

        if zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path) as archive:
                for info in sorted(archive.infolist(), key=lambda item: item.filename):
                    if info.is_dir() and not options.include_directories:
                        continue
                    if self._skip_member(info.filename, info.file_size, options):
                        continue
                    # KSRC-03: per-member ratio check. ZIP exposes both
                    # compressed and uncompressed sizes in the central
                    # directory, so the bomb is detectable without ever
                    # decompressing a single byte.
                    if (
                        max_ratio > 0
                        and info.compress_size > 0
                        and info.file_size / info.compress_size > max_ratio
                    ):
                        ratio_msg = (
                            f"Archive member {info.filename!r} exceeds "
                            f"decompression ratio cap "
                            f"({info.file_size}/{info.compress_size} > {max_ratio})"
                        )
                        raise SourceValidationError(
                            ratio_msg,
                            archive_path=str(archive_path),
                            member_path=info.filename,
                        )
                    # KSRC-03: cumulative cap. A single legitimate member
                    # is fine; ten thousand legitimate members summing to
                    # 50 TiB is a bomb.
                    total_uncompressed += info.file_size
                    if max_total and total_uncompressed > max_total:
                        raise SourceValidationError(
                            "Archive total uncompressed size exceeds cap "
                            f"({total_uncompressed} > {max_total})",
                            archive_path=str(archive_path),
                        )
                    entries.append(self._descriptor_for_zip_member(archive_path, info))
            return entries

        if tarfile.is_tarfile(archive_path):
            with tarfile.open(archive_path) as archive:
                for info in sorted(archive.getmembers(), key=lambda item: item.name):
                    if info.isdir() and not options.include_directories:
                        continue
                    # KSRC-06: skip TAR symlinks / hardlinks unless
                    # explicitly opted in. Blocks the ``../../etc/passwd``
                    # archive-escape attack vector. ZIP cannot encode
                    # symlinks at the format level.
                    if (info.issym() or info.islnk()) and not options.allow_symlinks:
                        logger.warning(
                            "Skipping TAR symlink/hardlink member %s (-> %s)",
                            info.name,
                            info.linkname,
                        )
                        continue
                    if self._skip_member(info.name, info.size, options):
                        continue
                    # KSRC-03: cumulative uncompressed cap. TAR doesn't
                    # have a per-entry compressed size in the same way
                    # ZIP does, so we can't compute a ratio here, but
                    # the total cap still applies.
                    total_uncompressed += info.size
                    if max_total and total_uncompressed > max_total:
                        raise SourceValidationError(
                            "Archive total uncompressed size exceeds cap "
                            f"({total_uncompressed} > {max_total})",
                            archive_path=str(archive_path),
                        )
                    entries.append(self._descriptor_for_tar_member(archive_path, info))
            return entries

        logger.warning("Unsupported archive format: %s", archive_path)
        raise SourceValidationError("Unsupported archive type", archive_path=str(archive_path))

    def _skip_member(self, member_name: str, size: int, options: SourceDiscoverOptions) -> bool:
        pure_path = PurePosixPath(member_name)
        if not options.include_hidden and any(part.startswith(".") for part in pure_path.parts):
            return True
        depth = len(pure_path.parts)
        if options.max_depth is not None and depth > options.max_depth:
            return True
        if options.min_size is not None and size < options.min_size:
            return True
        if options.max_size is not None and size > options.max_size:
            return True
        return not path_matches_patterns(member_name, options.patterns)

    def _descriptor_for_zip_member(
        self,
        archive_path: Path,
        info: zipfile.ZipInfo,
    ) -> SourceDescriptor:
        locator = SourceLocator.archive_member(archive_path, info.filename)
        return SourceDescriptor(
            source_id=locator.uri,
            source_kind=self.kind,
            locator=locator,
            name=PurePosixPath(info.filename).name,
            mime_type=guess_mime_type(info.filename),
            size=info.file_size,
            metadata={
                "kind": "directory" if info.is_dir() else "file",
                "member_path": info.filename,
            },
            provenance=self._provenance(
                locator,
                request_metadata={"archive_path": str(archive_path), "archive_format": "zip"},
            ),
            can_materialize=not info.is_dir(),
            preview_available=not info.is_dir(),
        )

    def _descriptor_for_tar_member(
        self,
        archive_path: Path,
        info: tarfile.TarInfo,
    ) -> SourceDescriptor:
        locator = SourceLocator.archive_member(archive_path, info.name)
        return SourceDescriptor(
            source_id=locator.uri,
            source_kind=self.kind,
            locator=locator,
            name=PurePosixPath(info.name).name,
            mime_type=guess_mime_type(info.name),
            size=info.size,
            metadata={"kind": "directory" if info.isdir() else "file", "member_path": info.name},
            provenance=self._provenance(
                locator,
                request_metadata={"archive_path": str(archive_path), "archive_format": "tar"},
            ),
            can_materialize=not info.isdir(),
            preview_available=not info.isdir(),
        )

    def _describe_member(self, archive_path: Path, member_path: str) -> SourceDescriptor:
        for descriptor in self._iter_members(
            archive_path, SourceDiscoverOptions(include_directories=True)
        ):
            if descriptor.locator.member_path == member_path:
                return descriptor
        raise SourceNotFoundError(
            "Archive member was not found",
            archive_path=str(archive_path),
            member_path=member_path,
        )

    def _read_member_preview(self, archive_path: Path, member_path: str, max_bytes: int) -> bytes:
        with self._open_member_stream(archive_path, member_path) as stream:
            return stream.read(max_bytes)

    def _open_member_stream(self, archive_path: Path, member_path: str) -> ReadableBinaryStream:
        if zipfile.is_zipfile(archive_path):
            archive = zipfile.ZipFile(archive_path)
            try:
                stream = archive.open(member_path, "r")
            except KeyError as exc:
                archive.close()
                raise SourceNotFoundError(
                    "Archive member was not found",
                    archive_path=str(archive_path),
                    member_path=member_path,
                ) from exc
            return _ArchiveStream(stream=cast(ReadableBinaryStream, stream), archive=archive)

        if tarfile.is_tarfile(archive_path):
            stack = contextlib.ExitStack()
            archive = stack.enter_context(self._open_tar_archive(archive_path))
            try:
                member = archive.getmember(member_path)
            except KeyError as exc:
                stack.close()
                raise SourceNotFoundError(
                    "Archive member was not found",
                    archive_path=str(archive_path),
                    member_path=member_path,
                ) from exc
            stream = archive.extractfile(member)
            if stream is None:
                stack.close()
                raise SourceValidationError(
                    "Archive member is not a regular file",
                    archive_path=str(archive_path),
                    member_path=member_path,
                )
            return _ArchiveStream(stream=cast(ReadableBinaryStream, stream), archive=stack)

        raise SourceValidationError("Unsupported archive type", archive_path=str(archive_path))

    @staticmethod
    def _archive_format(archive_path: Path) -> str:
        if zipfile.is_zipfile(archive_path):
            return "zip"
        if tarfile.is_tarfile(archive_path):
            return "tar"
        raise SourceValidationError("Unsupported archive type", archive_path=str(archive_path))

    @staticmethod
    @contextlib.contextmanager
    def _open_tar_archive(archive_path: Path) -> Iterator[tarfile.TarFile]:
        with tarfile.open(archive_path) as archive:
            yield archive


class _ArchiveStream:
    def __init__(self, *, stream: ReadableBinaryStream, archive: Closable) -> None:
        self._stream = stream
        self._archive = archive

    def read(self, size: int = -1) -> bytes:
        try:
            return self._stream.read(size)
        except OSError as exc:
            raise SourceAccessError("Failed to read archive member") from exc

    def close(self) -> None:
        self._stream.close()
        self._archive.close()

    def __enter__(self) -> _ArchiveStream:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        del exc_type, exc, tb
        self.close()
