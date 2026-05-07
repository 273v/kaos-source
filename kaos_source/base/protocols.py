"""Pure-strategy Protocols for kaos-source.

Protocols live here when there's no shared implementation worth
inheriting — the contract is purely structural ("has a method named X
with this signature"). ABCs (:mod:`kaos_source.base.connector`,
:mod:`kaos_source.base.api_connector`, :mod:`kaos_source.base.parser`)
live in their own modules when they carry shared behavior.

Two families:

- **Stream lifecycle** (:class:`Closable`, :class:`ReadableBinaryStream`)
  — historically defined inline in :mod:`kaos_source.connectors.base`;
  hoisted here so non-connector code (parsers, apis) can also depend
  on them without pulling in the connector hierarchy.
- **Capability shapes** (:class:`SupportsSearch`, :class:`SupportsGet`,
  :class:`SupportsPreview`, :class:`SupportsMaterialize`) — each
  :class:`ApiConnector` subclass declares which it satisfies via
  :attr:`ApiMetadata.capabilities`. Static type checkers can verify
  conformance via ``isinstance(conn, SupportsSearch)`` when these are
  ``runtime_checkable``.
"""

from __future__ import annotations

from typing import Any, Protocol, Self, runtime_checkable


@runtime_checkable
class Closable(Protocol):
    """Object that releases an underlying resource on ``close()``."""

    def close(self) -> None: ...


@runtime_checkable
class ReadableBinaryStream(Protocol):
    """Bytes stream supporting ``with``-block usage and bounded reads."""

    def read(self, size: int = -1) -> bytes: ...
    def close(self) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...


@runtime_checkable
class SupportsSearch(Protocol):
    """Capability marker: the API connector exposes ``search()``.

    Signatures vary by API (FR takes ``query``+``per_page``, EDGAR takes
    ``q``+``forms``+``dateRange``); the Protocol intentionally accepts
    arbitrary args so each connector keeps its idiomatic shape.
    Consumers should check :attr:`ApiMetadata.capabilities` for
    ``SourceCapability.SEARCH`` before calling.
    """

    async def search(self, *args: Any, **kwargs: Any) -> Any: ...


@runtime_checkable
class SupportsGet(Protocol):
    """Capability marker: the API connector exposes ``get()``."""

    async def get(self, *args: Any, **kwargs: Any) -> Any: ...


@runtime_checkable
class SupportsPreview(Protocol):
    """Capability marker: the API connector exposes ``preview()``.

    Preview returns a bounded slice of a remote resource without
    materializing the full body — the API equivalent of the metadata
    tier exposed by :class:`SourceConnector` for transport connectors.
    """

    async def preview(self, *args: Any, **kwargs: Any) -> Any: ...


@runtime_checkable
class SupportsMaterialize(Protocol):
    """Capability marker: the API connector exposes ``materialize()``.

    Materialize produces a :class:`SourceMaterialization` (artifact
    handle + manifest), unifying the API-fetch story with the transport
    connector story.
    """

    async def materialize(self, *args: Any, **kwargs: Any) -> Any: ...
