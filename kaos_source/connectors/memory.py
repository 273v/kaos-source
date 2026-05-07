from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any

from kaos_core import KaosContext

from kaos_source.connectors.base import (
    SourceConnector,
    decode_cursor,
    encode_cursor,
    guess_mime_type,
)
from kaos_source.errors import SourceNotFoundError, SourceValidationError
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


@dataclass(slots=True)
class _MemoryItem:
    name: str
    payload: bytes
    mime_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class MemoryConnector(SourceConnector):
    kind = SourceKind.MEMORY
    name = "memory"

    def __init__(self) -> None:
        self._items: dict[str, _MemoryItem] = {}

    def put_bytes(
        self,
        name: str,
        payload: bytes,
        *,
        mime_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SourceLocator:
        item = _MemoryItem(
            name=name,
            payload=payload,
            mime_type=mime_type or guess_mime_type(name),
            metadata=metadata or {},
        )
        self._items[name] = item
        return SourceLocator.memory(name)

    async def describe(self, locator: SourceLocator, context: KaosContext) -> SourceDescriptor:
        del context
        item = self._item(locator)
        locator = SourceLocator.memory(item.name)
        return SourceDescriptor(
            source_id=locator.uri,
            source_kind=self.kind,
            locator=locator,
            name=item.name,
            mime_type=item.mime_type,
            size=len(item.payload),
            metadata=item.metadata,
            provenance=self._provenance(locator),
            can_materialize=True,
            preview_available=True,
        )

    async def discover(
        self,
        locator: SourceLocator,
        context: KaosContext,
        options: SourceDiscoverOptions | None = None,
    ) -> SourcePage:
        options = options or SourceDiscoverOptions()
        if locator.name is not None:
            if decode_cursor(options.cursor) > 0:
                return SourcePage(items=[])
            return SourcePage(items=[await self.describe(locator, context)])

        names = sorted(self._items)
        start_offset = decode_cursor(options.cursor)
        page_names = names[start_offset : start_offset + options.limit]
        next_cursor = None
        if start_offset + options.limit < len(names):
            next_cursor = encode_cursor(start_offset + options.limit)
        return SourcePage(
            items=[await self.describe(SourceLocator.memory(name), context) for name in page_names],
            next_cursor=next_cursor,
            total_count=len(names),
        )

    async def preview(
        self,
        locator: SourceLocator,
        context: KaosContext,
        options: SourcePreviewOptions | None = None,
    ) -> SourcePreview:
        options = options or SourcePreviewOptions()
        item = self._item(locator)
        descriptor = await self.describe(SourceLocator.memory(item.name), context)
        payload = item.payload[: options.max_bytes]
        return self._decode_preview_payload(
            payload,
            source_id=descriptor.source_id,
            size=len(item.payload),
            mime_type=item.mime_type,
            encoding=options.encoding,
        )

    async def materialize(
        self,
        locator: SourceLocator,
        context: KaosContext,
        options: SourceMaterializeOptions | None = None,
    ) -> SourceMaterialization:
        options = options or SourceMaterializeOptions()
        item = self._item(locator)
        descriptor = await self.describe(SourceLocator.memory(item.name), context)
        # ``io.BytesIO`` is structurally a binary stream but ty's per-module
        # type resolution rejects the lambda's return against the protocol.
        # The runtime contract is correct; covered by unit tests.
        return await self._materialize_stream(
            stream_factory=lambda: io.BytesIO(item.payload),  # ty: ignore[invalid-argument-type]
            context=context,
            descriptor=descriptor,
            options=options,
        )

    def _item(self, locator: SourceLocator) -> _MemoryItem:
        if locator.name is None:
            raise SourceValidationError("Memory locator requires a name", locator=locator.uri)
        try:
            return self._items[locator.name]
        except KeyError as exc:
            raise SourceNotFoundError(
                "Unknown memory source", locator=locator.uri, name=locator.name
            ) from exc
