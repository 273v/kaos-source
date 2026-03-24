from __future__ import annotations

import asyncio
import base64
import mimetypes
import shutil
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from typing import Protocol, Self
from urllib.parse import unquote, urlparse, urlsplit
from uuid import uuid4

from kaos_core import ArtifactRetentionPolicy, KaosContext
from kaos_core.protocol.roots import Root

from kaos_source.errors import (
    SourceMaterializationError,
    SourceNotFoundError,
    SourcePolicyError,
    SourceValidationError,
)
from kaos_source.models import (
    SourceDescriptor,
    SourceKind,
    SourceLocator,
    SourceMaterialization,
    SourcePage,
    SourcePreview,
    SourceProvenance,
)
from kaos_source.options import (
    SourceDiscoverOptions,
    SourceMaterializeOptions,
    SourcePreviewOptions,
)


class Closable(Protocol):
    def close(self) -> None: ...


class ReadableBinaryStream(Protocol):
    def read(self, size: int = -1) -> bytes: ...
    def close(self) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...


def now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def timestamp_to_iso(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()


def guess_mime_type(name: str, fallback: str | None = None) -> str | None:
    mime_type, _ = mimetypes.guess_type(name)
    return mime_type or fallback


def encode_cursor(offset: int) -> str:
    raw = f"offset:{offset}".encode()
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        prefix, value = decoded.split(":", 1)
    except Exception as exc:
        raise SourceValidationError("Invalid discovery cursor", cursor=cursor) from exc
    if prefix != "offset" or not value.isdigit():
        raise SourceValidationError("Invalid discovery cursor", cursor=cursor)
    return int(value)


def path_matches_patterns(path: str, patterns: list[str]) -> bool:
    if not patterns:
        return True
    return any(
        fnmatch(path, pattern) or fnmatch(PurePosixPath(path).name, pattern) for pattern in patterns
    )


def _root_path(root: Root) -> Path | None:
    parsed = urlparse(root.uri)
    if parsed.scheme != "file":
        return None
    return Path(unquote(parsed.path or "/")).resolve()


def assert_roots_allow_path(path: Path, roots: list[Root] | None) -> None:
    if not roots:
        return
    resolved_path = path.resolve()
    root_paths = [root_path for root in roots if (root_path := _root_path(root)) is not None]
    if not root_paths:
        raise SourcePolicyError("Source access denied by roots policy", path=str(resolved_path))
    for root_path in root_paths:
        try:
            resolved_path.relative_to(root_path)
        except ValueError:
            continue
        return
    raise SourcePolicyError("Source access denied by roots policy", path=str(resolved_path))


def assert_roots_allow_uri(uri: str, roots: list[Root] | None, *, schemes: set[str]) -> None:
    if not roots:
        return

    parsed_uri = urlsplit(uri)
    relevant_roots = [root for root in roots if urlsplit(root.uri).scheme.lower() in schemes]
    if not relevant_roots:
        return

    request_scheme = parsed_uri.scheme.lower()
    request_netloc = parsed_uri.netloc.lower()
    request_path = PurePosixPath(parsed_uri.path or "/").as_posix()

    for root in relevant_roots:
        parsed_root = urlsplit(root.uri)
        root_scheme = parsed_root.scheme.lower()
        root_netloc = parsed_root.netloc.lower()
        root_path = PurePosixPath(parsed_root.path or "/").as_posix()
        if request_scheme != root_scheme or request_netloc != root_netloc:
            continue
        normalized_root = root_path.rstrip("/") or "/"
        if normalized_root == "/":
            return
        if request_path == normalized_root or request_path.startswith(f"{normalized_root}/"):
            return

    raise SourcePolicyError("Source access denied by roots policy", uri=uri)


def ensure_file_exists(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.exists():
        raise SourceNotFoundError("Source path does not exist", path=str(resolved))
    return resolved


def ensure_directory(path: Path) -> Path:
    resolved = ensure_file_exists(path)
    if not resolved.is_dir():
        raise SourceValidationError("Source path is not a directory", path=str(resolved))
    return resolved


def ensure_regular_file(path: Path) -> Path:
    resolved = ensure_file_exists(path)
    if not resolved.is_file():
        raise SourceValidationError("Source path is not a file", path=str(resolved))
    return resolved


class SourceConnector(ABC):
    kind: SourceKind
    name: str

    @abstractmethod
    async def describe(self, locator: SourceLocator, context: KaosContext) -> SourceDescriptor:
        raise NotImplementedError

    @abstractmethod
    async def discover(
        self,
        locator: SourceLocator,
        context: KaosContext,
        options: SourceDiscoverOptions | None = None,
    ) -> SourcePage:
        raise NotImplementedError

    @abstractmethod
    async def preview(
        self,
        locator: SourceLocator,
        context: KaosContext,
        options: SourcePreviewOptions | None = None,
    ) -> SourcePreview:
        raise NotImplementedError

    @abstractmethod
    async def materialize(
        self,
        locator: SourceLocator,
        context: KaosContext,
        options: SourceMaterializeOptions | None = None,
    ) -> SourceMaterialization:
        raise NotImplementedError

    async def cleanup(self, context: KaosContext) -> None:
        del context

    def _require_runtime(self, context: KaosContext) -> None:
        if context.runtime is None:
            raise SourceValidationError("Context must be attached to a runtime")

    def _require_path(self, locator: SourceLocator, *, field: str = "path") -> str:
        value = getattr(locator, field)
        if not isinstance(value, str) or not value:
            raise SourceValidationError(
                "Source locator is missing required path data",
                field=field,
                locator=locator.uri,
            )
        return value

    def _provenance(
        self,
        locator: SourceLocator,
        *,
        request_metadata: dict[str, object] | None = None,
        parent_artifact_id: str | None = None,
    ) -> SourceProvenance:
        return SourceProvenance(
            source_kind=locator.source_kind,
            locator=locator,
            connector_name=self.name,
            retrieved_at=now_iso(),
            request_metadata=request_metadata or {},
            parent_artifact_id=parent_artifact_id,
        )

    async def _materialize_local_path(
        self,
        *,
        source_path: Path,
        context: KaosContext,
        descriptor: SourceDescriptor,
        options: SourceMaterializeOptions,
    ) -> SourceMaterialization:
        self._require_runtime(context)
        assert context.runtime is not None

        target_path = options.target_path or self._default_target_path(descriptor.name, self.kind)
        target_relative_path = context.vfs.normalize_path(target_path)
        target_disk_path = context.vfs.resolve_disk_path(
            target_relative_path, context_id=context.session_id
        )

        try:
            if target_disk_path is not None:
                await asyncio.to_thread(self._copy_path_to_disk, source_path, target_disk_path)
            else:
                payload = await asyncio.to_thread(source_path.read_bytes)
                await context.vfs.write(
                    target_relative_path, payload, context_id=context.session_id
                )
        except OSError as exc:
            raise SourceMaterializationError(
                "Failed to stage source into VFS",
                source_path=str(source_path),
                target_path=target_relative_path,
            ) from exc

        manifest = await context.runtime.artifacts.create_from_path(
            target_relative_path,
            context_id=context.session_id,
            session_id=context.session_id,
            workflow_id=options.workflow_id,
            name=options.artifact_name or descriptor.name,
            description=options.artifact_description,
            mime_type=descriptor.mime_type,
            role=options.role,
            provenance=descriptor.provenance.model_dump(mode="json"),
            retention_policy=options.retention_policy,
            metadata=options.metadata,
            checksum=options.checksum,
            ttl_seconds=options.ttl_seconds,
        )
        return SourceMaterialization(
            descriptor=descriptor,
            manifest=manifest,
            artifact_ref=manifest.to_ref(),
            bytes_written=manifest.size,
            retention_policy=ArtifactRetentionPolicy(manifest.retention_policy),
        )

    async def _materialize_stream(
        self,
        *,
        stream_factory: Callable[[], ReadableBinaryStream],
        context: KaosContext,
        descriptor: SourceDescriptor,
        options: SourceMaterializeOptions,
    ) -> SourceMaterialization:
        self._require_runtime(context)
        assert context.runtime is not None

        target_path = options.target_path or self._default_target_path(descriptor.name, self.kind)
        target_relative_path = context.vfs.normalize_path(target_path)
        target_disk_path = context.vfs.resolve_disk_path(
            target_relative_path, context_id=context.session_id
        )
        if target_disk_path is None:
            try:
                payload = await asyncio.to_thread(self._read_stream_bytes, stream_factory)
            except OSError as exc:
                raise SourceMaterializationError(
                    "Failed to read source stream for materialization",
                    locator=descriptor.locator.uri,
                ) from exc
            await context.vfs.write(target_relative_path, payload, context_id=context.session_id)
        else:
            try:
                await asyncio.to_thread(self._copy_stream_to_disk, stream_factory, target_disk_path)
            except OSError as exc:
                raise SourceMaterializationError(
                    "Failed to copy source stream into VFS",
                    locator=descriptor.locator.uri,
                    target_path=target_relative_path,
                ) from exc

        manifest = await context.runtime.artifacts.create_from_path(
            target_relative_path,
            context_id=context.session_id,
            session_id=context.session_id,
            workflow_id=options.workflow_id,
            name=options.artifact_name or descriptor.name,
            description=options.artifact_description,
            mime_type=descriptor.mime_type,
            role=options.role,
            provenance=descriptor.provenance.model_dump(mode="json"),
            retention_policy=options.retention_policy,
            metadata=options.metadata,
            checksum=options.checksum,
            ttl_seconds=options.ttl_seconds,
        )
        return SourceMaterialization(
            descriptor=descriptor,
            manifest=manifest,
            artifact_ref=manifest.to_ref(),
            bytes_written=manifest.size,
            retention_policy=ArtifactRetentionPolicy(manifest.retention_policy),
        )

    async def _materialize_bytes(
        self,
        *,
        payload: bytes,
        context: KaosContext,
        descriptor: SourceDescriptor,
        options: SourceMaterializeOptions,
        artifact_name: str | None = None,
        artifact_description: str | None = None,
        target_path: str | None = None,
        mime_type: str | None = None,
        metadata: dict[str, object] | None = None,
        provenance: dict[str, object] | None = None,
    ) -> SourceMaterialization:
        self._require_runtime(context)
        assert context.runtime is not None

        resolved_target_path = target_path or self._default_target_path(descriptor.name, self.kind)
        target_relative_path = context.vfs.normalize_path(resolved_target_path)
        await context.vfs.write(target_relative_path, payload, context_id=context.session_id)

        manifest = await context.runtime.artifacts.create_from_path(
            target_relative_path,
            context_id=context.session_id,
            session_id=context.session_id,
            workflow_id=options.workflow_id,
            name=artifact_name or options.artifact_name or descriptor.name,
            description=artifact_description or options.artifact_description,
            mime_type=mime_type or descriptor.mime_type,
            role=options.role,
            provenance=provenance or descriptor.provenance.model_dump(mode="json"),
            retention_policy=options.retention_policy,
            metadata=options.metadata if metadata is None else metadata,
            checksum=options.checksum,
            ttl_seconds=options.ttl_seconds,
        )
        return SourceMaterialization(
            descriptor=descriptor,
            manifest=manifest,
            artifact_ref=manifest.to_ref(),
            bytes_written=manifest.size,
            retention_policy=ArtifactRetentionPolicy(manifest.retention_policy),
        )

    @staticmethod
    def _copy_path_to_disk(source_path: Path, target_path: Path) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target_path)

    @staticmethod
    def _copy_stream_to_disk(
        stream_factory: Callable[[], ReadableBinaryStream],
        target_path: Path,
    ) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with stream_factory() as source, target_path.open("wb") as target:
            shutil.copyfileobj(source, target)

    @staticmethod
    def _read_stream_bytes(stream_factory: Callable[[], ReadableBinaryStream]) -> bytes:
        with stream_factory() as source:
            return source.read()

    @staticmethod
    def _default_target_path(name: str, kind: SourceKind) -> str:
        safe_name = "".join(
            char if char.isalnum() or char in {"-", "_", "."} else "-" for char in name
        )
        safe_name = safe_name.strip("-") or "artifact"
        return f"sources/{kind.value}/{uuid4()}-{safe_name}"

    @staticmethod
    def _decode_preview_payload(
        payload: bytes,
        *,
        source_id: str,
        size: int | None,
        mime_type: str | None,
        encoding: str,
        truncated_override: bool | None = None,
    ) -> SourcePreview:
        truncated = (
            truncated_override
            if truncated_override is not None
            else (size is not None and size > len(payload))
        )
        is_text = False
        if mime_type is not None:
            is_text = mime_type.startswith("text/") or mime_type in {
                "application/json",
                "application/xml",
                "application/yaml",
            }
        if not is_text and b"\x00" not in payload:
            is_text = True
        if is_text:
            return SourcePreview(
                source_id=source_id,
                text_preview=payload.decode(encoding, errors="replace"),
                truncated=truncated,
                size=size,
                mime_type=mime_type,
            )
        return SourcePreview.from_binary(
            source_id=source_id,
            payload=payload,
            truncated=truncated,
            size=size,
            mime_type=mime_type,
        )
