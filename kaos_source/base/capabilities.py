"""SourceCapability enum — declared on :class:`ConnectorMetadata` /
:class:`ApiMetadata` / :class:`ParserMetadata` to advertise which
operations the concrete subclass implements.

Use as a precondition check before calling capability-shape methods:

.. code-block:: python

    if SourceCapability.SEARCH in connector.metadata().capabilities:
        results = await connector.search(query)

Today's :class:`SourceConnector` ABC requires *all* of describe /
discover / preview / materialize. :class:`ApiConnector` is intentionally
looser — APIs vary in what they expose (e.g. GLEIF has search + get but
no preview tier), so capabilities are advertised explicitly per class.
"""

from __future__ import annotations

from enum import StrEnum


class SourceCapability(StrEnum):
    """Operations a source/api/parser may advertise."""

    DESCRIBE = "describe"
    """Return metadata for a single source without reading its body."""

    DISCOVER = "discover"
    """Paginate over items at a source root (filesystem, archive, search)."""

    PREVIEW = "preview"
    """Return a bounded read of a single source's body."""

    MATERIALIZE = "materialize"
    """Stage the source body into a VFS-backed :class:`ArtifactManifest`."""

    SEARCH = "search"
    """Free-text or structured search against a remote API."""

    GET = "get"
    """Fetch a structured record by identifier from a remote API."""

    RESOLVE = "resolve"
    """Map an external identifier (LEI, CIK, citation) to a canonical record."""

    PARSE = "parse"
    """Decode a raw byte stream into typed records (vCard, EML, EXIF)."""
