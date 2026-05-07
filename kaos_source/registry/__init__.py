"""Catalogues for kaos-source core concepts.

Mirrors :mod:`kaos_agents.registry`. Each registry holds either
instances or classes keyed by their identity (``SourceKind`` for
transport connectors, ``metadata().name`` for api connectors and
parsers) and surfaces lookup, listing, and filtering helpers.

Three registries (added in Track 1 chunk 4):

- :mod:`kaos_source.registry.connector_registry` —
  :class:`ConnectorRegistry`
  Holds :class:`SourceConnector` instances keyed by :class:`SourceKind`
  for the transport layer (filesystem / archive / http / browser /
  memory). Routed via :class:`SourceService`.

- :mod:`kaos_source.registry.api_registry` —
  :class:`ApiRegistry`
  Holds :class:`ApiConnector` *classes* keyed by name (e.g.
  ``"federal_register"``, ``"ecfr"``) for the REST API layer. Holds
  classes (not instances) because each call typically constructs a
  fresh httpx client; class-level holding lets callers pass settings
  per-call. Populated by :mod:`kaos_source.apis` on import (chunk 5).

- :mod:`kaos_source.registry.parser_registry` —
  :class:`ParserRegistry`
  Holds :class:`SourceParser` *classes* keyed by name, with a
  secondary MIME-type index for content-type-based routing.
  Populated by :mod:`kaos_source.parsers` on import (chunk 6).

Auto-registration uses explicit calls (not ``__init_subclass__``)
matching the kaos-agents Track 2 discipline:

- We want exactly the canonical concrete types in the default
  registries, not every subclass anyone happens to create.
- Tests subclass ABCs for fixtures; auto-registration would pollute
  the default registries with test-private classes.

For out-of-tree custom connectors / apis / parsers, register
explicitly::

    from kaos_source.registry import default_api_registry
    default_api_registry.register("custom_api", MyCustomApiConnector)
"""

from __future__ import annotations

from kaos_source.registry.api_registry import (
    ApiRegistry,
    default_api_registry,
)
from kaos_source.registry.connector_registry import (
    ConnectorRegistry,
    default_connector_registry,
)
from kaos_source.registry.parser_registry import (
    ParserRegistry,
    default_parser_registry,
)

__all__ = [
    "ApiRegistry",
    "ConnectorRegistry",
    "ParserRegistry",
    "default_api_registry",
    "default_connector_registry",
    "default_parser_registry",
]
