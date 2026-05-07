"""Abstract base classes (ABCs) and Protocols for kaos-source core concepts.

Mirrors the layout of :mod:`kaos_agents.base` (Track 2 chunk 1) and
:mod:`kaos_core.base`. Each concept's ABC carries a frozen pydantic
``KaosModel`` metadata describing its identity, returned via a
``metadata()`` classmethod. Pure-strategy contracts (no shared
implementation) are :class:`typing.Protocol` classes.

The three concepts (added incrementally across the refactor):

- :mod:`kaos_source.base.connector` — :class:`SourceConnector` (chunk 2 moves
  the existing ``connectors/base.py`` ABC here, slimmed)
- :mod:`kaos_source.base.api_connector` — :class:`ApiConnector` (chunk 1, NEW)
- :mod:`kaos_source.base.parser` — :class:`SourceParser` (chunk 1, NEW)

Pure-strategy contracts in :mod:`kaos_source.base.protocols`:

- :class:`Closable` / :class:`ReadableBinaryStream` — stream lifecycle
- :class:`SupportsSearch` / :class:`SupportsGet` / :class:`SupportsPreview`
  / :class:`SupportsMaterialize` — capability shape checks for ApiConnector

Value types in :mod:`kaos_source.base.metadata` (frozen pydantic):

- :class:`ConnectorMetadata`, :class:`ApiMetadata`, :class:`ParserMetadata`

Capability enum in :mod:`kaos_source.base.capabilities`:

- :class:`SourceCapability`

Dependency direction: ``base/`` MUST NOT import from ``runtime/``,
``connectors/``, ``apis/``, or ``parsers/``. This keeps the contracts
package side-effect-free and prevents import cycles.
"""

from __future__ import annotations

from kaos_source.base.api_connector import ApiConnector
from kaos_source.base.capabilities import SourceCapability
from kaos_source.base.metadata import (
    ApiMetadata,
    ConnectorMetadata,
    ParserMetadata,
)
from kaos_source.base.parser import SourceParser
from kaos_source.base.protocols import (
    Closable,
    ReadableBinaryStream,
    SupportsGet,
    SupportsMaterialize,
    SupportsPreview,
    SupportsSearch,
)

__all__ = [
    "ApiConnector",
    "ApiMetadata",
    "Closable",
    "ConnectorMetadata",
    "ParserMetadata",
    "ReadableBinaryStream",
    "SourceCapability",
    "SourceParser",
    "SupportsGet",
    "SupportsMaterialize",
    "SupportsPreview",
    "SupportsSearch",
]
