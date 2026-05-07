"""Connector ABC + back-compat re-exports.

After Track 1 chunk 2 the bulk of this module's old contents lives in
:mod:`kaos_source.runtime` (free-function helpers) and
:mod:`kaos_source.base.protocols` (Closable / ReadableBinaryStream).
What remains here is:

- :class:`SourceConnector` ABC — the contract the 5 transport
  connectors implement. Materialization helper methods are kept on the
  class for back-compat (test_hardening.py uses them; the 5 transport
  connectors call them via ``self``); their bodies delegate to the
  free functions in :mod:`kaos_source.runtime.materialization` /
  :mod:`kaos_source.runtime.preview_decode`.
- Re-exports of the moved utilities (``now_iso`` / ``timestamp_to_iso``,
  ``guess_mime_type``, ``encode_cursor`` / ``decode_cursor``,
  ``path_matches_patterns``, ``assert_roots_allow_path`` /
  ``assert_roots_allow_uri``, ``ensure_*``, ``Closable``,
  ``ReadableBinaryStream``) so any existing
  ``from kaos_source.connectors.base import X`` continues to resolve.

Chunk 7 closeout will move :class:`SourceConnector` into
:mod:`kaos_source.base.connector` (slim) once the test suite migrates
off the back-compat surface; for now keeping the class here preserves
the public API exactly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from kaos_core import KaosContext

from kaos_source.base.protocols import Closable, ReadableBinaryStream
from kaos_source.errors import SourceValidationError
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
from kaos_source.runtime.cursor import decode_cursor, encode_cursor
from kaos_source.runtime.materialization import (
    default_target_path,
    materialize_bytes,
    materialize_local_path,
    materialize_stream,
)
from kaos_source.runtime.mime import guess_mime_type
from kaos_source.runtime.policy import (
    assert_roots_allow_path,
    assert_roots_allow_uri,
    ensure_directory,
    ensure_file_exists,
    ensure_regular_file,
    path_matches_patterns,
)
from kaos_source.runtime.preview_decode import decode_preview_payload
from kaos_source.runtime.time import now_iso, timestamp_to_iso

if TYPE_CHECKING:
    pass


__all__ = [
    "Closable",
    "ReadableBinaryStream",
    "SourceConnector",
    "assert_roots_allow_path",
    "assert_roots_allow_uri",
    "decode_cursor",
    "encode_cursor",
    "ensure_directory",
    "ensure_file_exists",
    "ensure_regular_file",
    "guess_mime_type",
    "now_iso",
    "path_matches_patterns",
    "timestamp_to_iso",
]


class SourceConnector(ABC):
    """ABC every transport :class:`SourceConnector` (filesystem / archive /
    http / browser / memory) implements.

    Required overrides: :meth:`describe`, :meth:`discover`,
    :meth:`preview`, :meth:`materialize`. Subclasses set the class-level
    :attr:`kind` and :attr:`name` attributes for routing and provenance.
    """

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
        return await materialize_local_path(
            connector_kind=self.kind,
            source_path=source_path,
            context=context,
            descriptor=descriptor,
            options=options,
        )

    async def _materialize_stream(
        self,
        *,
        stream_factory: Callable[[], ReadableBinaryStream],
        context: KaosContext,
        descriptor: SourceDescriptor,
        options: SourceMaterializeOptions,
    ) -> SourceMaterialization:
        return await materialize_stream(
            connector_kind=self.kind,
            stream_factory=stream_factory,
            context=context,
            descriptor=descriptor,
            options=options,
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
        return await materialize_bytes(
            connector_kind=self.kind,
            payload=payload,
            context=context,
            descriptor=descriptor,
            options=options,
            artifact_name=artifact_name,
            artifact_description=artifact_description,
            target_path=target_path,
            mime_type=mime_type,
            metadata=metadata,
            provenance=provenance,
        )

    @staticmethod
    def _default_target_path(name: str, kind: SourceKind) -> str:
        return default_target_path(name, kind)

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
        return decode_preview_payload(
            payload,
            source_id=source_id,
            size=size,
            mime_type=mime_type,
            encoding=encoding,
            truncated_override=truncated_override,
        )
