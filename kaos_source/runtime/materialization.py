"""Free-function materialization helpers — stage source bytes into the VFS.

Three entry points covering the byte-source taxonomy:

- :func:`materialize_local_path`   — already-on-disk file → VFS artifact
- :func:`materialize_stream`       — opened binary stream → VFS artifact
- :func:`materialize_bytes`        — in-memory payload → VFS artifact

Each returns a :class:`SourceMaterialization` (descriptor + manifest +
artifact_ref + retention policy). The functions take the connector's
``kind`` and ``name`` as explicit parameters so they're decoupled from
:class:`SourceConnector` instance state — chunks 5 and 6 use them
directly from :class:`ApiConnector` and :class:`SourceParser` subclasses
that don't extend :class:`SourceConnector`.

:class:`SourceConnector` (in :mod:`kaos_source.connectors.base`) keeps
thin method wrappers (``self._materialize_local_path``,
``self._materialize_stream``, ``self._materialize_bytes``) for the 5
transport connectors that already call them as instance methods. Those
wrappers delegate to these free functions.
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from kaos_core import ArtifactRetentionPolicy, KaosContext

from kaos_source.base.protocols import ReadableBinaryStream
from kaos_source.errors import SourceMaterializationError, SourceValidationError
from kaos_source.models import (
    SourceDescriptor,
    SourceKind,
    SourceMaterialization,
)
from kaos_source.options import SourceMaterializeOptions


def default_target_path(name: str, kind: SourceKind) -> str:
    """Generate a filesystem-safe ``sources/{kind}/{uuid}-{name}`` target path.

    Used as the fallback when ``SourceMaterializeOptions.target_path`` is
    not supplied. The name is sanitised: only ``[A-Za-z0-9._-]`` survive,
    everything else collapses to ``-``.
    """
    safe_name = "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in name)
    safe_name = safe_name.strip("-") or "artifact"
    return f"sources/{kind.value}/{uuid4()}-{safe_name}"


def copy_path_to_disk(source_path: Path, target_path: Path) -> None:
    """Synchronous file copy — used inside ``asyncio.to_thread``."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, target_path)


def copy_stream_to_disk(
    stream_factory: Callable[[], ReadableBinaryStream],
    target_path: Path,
) -> None:
    """Synchronous stream copy — used inside ``asyncio.to_thread``."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with stream_factory() as source, target_path.open("wb") as target:
        shutil.copyfileobj(source, target)


def read_stream_bytes(stream_factory: Callable[[], ReadableBinaryStream]) -> bytes:
    """Synchronous full-stream read — used inside ``asyncio.to_thread``."""
    with stream_factory() as source:
        return source.read()


def _require_runtime(context: KaosContext) -> None:
    """Guard: VFS materialization needs a runtime-attached context."""
    if context.runtime is None:
        raise SourceValidationError("Context must be attached to a runtime")


async def materialize_local_path(
    *,
    connector_kind: SourceKind,
    source_path: Path,
    context: KaosContext,
    descriptor: SourceDescriptor,
    options: SourceMaterializeOptions,
) -> SourceMaterialization:
    """Stage an on-disk file into the VFS and produce an artifact manifest."""
    _require_runtime(context)
    assert context.runtime is not None

    target_path = options.target_path or default_target_path(descriptor.name, connector_kind)
    target_relative_path = context.vfs.normalize_path(target_path)
    target_disk_path = context.vfs.resolve_disk_path(
        target_relative_path, context_id=context.session_id
    )

    try:
        if target_disk_path is not None:
            await asyncio.to_thread(copy_path_to_disk, source_path, target_disk_path)
        else:
            payload = await asyncio.to_thread(source_path.read_bytes)
            await context.vfs.write(target_relative_path, payload, context_id=context.session_id)
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


async def materialize_stream(
    *,
    connector_kind: SourceKind,
    stream_factory: Callable[[], ReadableBinaryStream],
    context: KaosContext,
    descriptor: SourceDescriptor,
    options: SourceMaterializeOptions,
) -> SourceMaterialization:
    """Stage a streaming source (opened on demand) into the VFS."""
    _require_runtime(context)
    assert context.runtime is not None

    target_path = options.target_path or default_target_path(descriptor.name, connector_kind)
    target_relative_path = context.vfs.normalize_path(target_path)
    target_disk_path = context.vfs.resolve_disk_path(
        target_relative_path, context_id=context.session_id
    )
    if target_disk_path is None:
        try:
            payload = await asyncio.to_thread(read_stream_bytes, stream_factory)
        except OSError as exc:
            raise SourceMaterializationError(
                "Failed to read source stream for materialization",
                locator=descriptor.locator.uri,
            ) from exc
        await context.vfs.write(target_relative_path, payload, context_id=context.session_id)
    else:
        try:
            await asyncio.to_thread(copy_stream_to_disk, stream_factory, target_disk_path)
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


async def materialize_bytes(
    *,
    connector_kind: SourceKind,
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
    """Stage in-memory bytes into the VFS — used by HTTP / browser / API connectors."""
    _require_runtime(context)
    assert context.runtime is not None

    resolved_target_path = target_path or default_target_path(descriptor.name, connector_kind)
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
