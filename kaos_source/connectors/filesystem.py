from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

from kaos_core import KaosContext

from kaos_source.connectors.base import (
    SourceConnector,
    assert_roots_allow_path,
    decode_cursor,
    encode_cursor,
    ensure_directory,
    ensure_file_exists,
    ensure_regular_file,
    guess_mime_type,
    path_matches_patterns,
    timestamp_to_iso,
)
from kaos_source.errors import SourceAccessError, SourceValidationError
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


class FilesystemConnector(SourceConnector):
    kind = SourceKind.FILESYSTEM
    name = "filesystem"

    async def describe(self, locator: SourceLocator, context: KaosContext) -> SourceDescriptor:
        source_path = Path(self._require_path(locator))
        resolved = await asyncio.to_thread(ensure_file_exists, source_path)
        assert_roots_allow_path(resolved, context.roots)
        return await asyncio.to_thread(self._descriptor_for_path, resolved)

    async def discover(
        self,
        locator: SourceLocator,
        context: KaosContext,
        options: SourceDiscoverOptions | None = None,
    ) -> SourcePage:
        options = options or SourceDiscoverOptions()
        source_path = Path(self._require_path(locator))
        resolved = await asyncio.to_thread(ensure_file_exists, source_path)
        assert_roots_allow_path(resolved, context.roots)
        start_offset = decode_cursor(options.cursor)

        if resolved.is_file():
            descriptor = await asyncio.to_thread(self._descriptor_for_path, resolved)
            if start_offset > 0:
                return SourcePage(items=[])
            return SourcePage(items=[descriptor])

        root_directory = await asyncio.to_thread(ensure_directory, resolved)
        page_items, next_cursor = await asyncio.to_thread(
            self._discover_directory_page,
            root_directory,
            options,
            start_offset,
        )
        return SourcePage(items=page_items, next_cursor=next_cursor)

    async def preview(
        self,
        locator: SourceLocator,
        context: KaosContext,
        options: SourcePreviewOptions | None = None,
    ) -> SourcePreview:
        options = options or SourcePreviewOptions()
        descriptor = await self.describe(locator, context)
        if descriptor.metadata.get("kind") != "file":
            raise SourceValidationError(
                "Filesystem preview is only available for files",
                locator=locator.uri,
            )
        source_path = Path(self._require_path(locator))
        resolved = await asyncio.to_thread(ensure_regular_file, source_path)
        payload = await asyncio.to_thread(self._read_preview, resolved, options.max_bytes)
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
        if descriptor.metadata.get("kind") != "file":
            raise SourceValidationError(
                "Filesystem materialization is only available for files",
                locator=locator.uri,
            )
        source_path = Path(self._require_path(locator))
        resolved = await asyncio.to_thread(ensure_regular_file, source_path)
        return await self._materialize_local_path(
            source_path=resolved,
            context=context,
            descriptor=descriptor,
            options=options,
        )

    def _discover_directory_page(
        self,
        root_directory: Path,
        options: SourceDiscoverOptions,
        start_offset: int,
    ) -> tuple[list[SourceDescriptor], str | None]:
        collected: list[SourceDescriptor] = []
        matched = 0
        next_cursor: str | None = None
        root_directory = root_directory.resolve()

        for path in self._walk_directory(root_directory, options):
            if matched < start_offset:
                matched += 1
                continue
            if len(collected) >= options.limit:
                next_cursor = encode_cursor(matched)
                break
            collected.append(self._descriptor_for_path(path))
            matched += 1

        return collected, next_cursor

    def _walk_directory(
        self, root_directory: Path, options: SourceDiscoverOptions
    ) -> Iterator[Path]:
        stack = [root_directory]

        while stack:
            current = stack.pop()
            try:
                children = sorted(current.iterdir(), key=lambda item: item.name)
            except OSError as exc:
                raise SourceAccessError(
                    "Failed to enumerate filesystem source",
                    path=str(current),
                ) from exc

            child_directories: list[Path] = []
            for child in children:
                relative = child.relative_to(root_directory).as_posix()
                depth = len(PurePosixPath(relative).parts)
                if not options.include_hidden and any(
                    part.startswith(".") for part in PurePosixPath(relative).parts
                ):
                    continue
                if options.max_depth is not None and depth > options.max_depth:
                    continue

                if child.is_dir():
                    if options.recursive:
                        child_directories.append(child)
                    if not options.include_directories:
                        continue
                if not path_matches_patterns(relative, options.patterns):
                    continue
                try:
                    stat = child.stat()
                except OSError as exc:
                    raise SourceAccessError(
                        "Failed to stat filesystem source",
                        path=str(child),
                    ) from exc
                if options.min_size is not None and stat.st_size < options.min_size:
                    continue
                if options.max_size is not None and stat.st_size > options.max_size:
                    continue
                yield child

            for child_directory in reversed(child_directories):
                stack.append(child_directory)

    def _descriptor_for_path(self, source_path: Path) -> SourceDescriptor:
        stat = source_path.stat()
        locator = SourceLocator.filesystem(source_path)
        kind = "directory" if source_path.is_dir() else "file"
        return SourceDescriptor(
            source_id=locator.uri,
            source_kind=self.kind,
            locator=locator,
            name=source_path.name or source_path.as_posix(),
            mime_type=guess_mime_type(source_path.name),
            size=stat.st_size,
            created_at=timestamp_to_iso(stat.st_ctime),
            modified_at=timestamp_to_iso(stat.st_mtime),
            metadata={
                "kind": kind,
                "path": str(source_path),
                "is_symlink": source_path.is_symlink(),
            },
            provenance=self._provenance(
                locator, request_metadata={"resolved_path": str(source_path)}
            ),
            can_materialize=kind == "file",
            preview_available=kind == "file",
        )

    @staticmethod
    def _read_preview(source_path: Path, max_bytes: int) -> bytes:
        try:
            with source_path.open("rb") as handle:
                return handle.read(max_bytes)
        except OSError as exc:
            raise SourceAccessError(
                "Failed to read filesystem source preview", path=str(source_path)
            ) from exc
