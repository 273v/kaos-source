"""REST API connectors — :class:`ApiConnector` implementations.

Track 1 chunk 5 reorganized the per-API code that used to live in
``kaos_source/connectors/<name>.py`` (functions + dataclasses) and
``kaos_source/tools_<name>.py`` (MCP tool classes) into focused
subpackages here. Each subpackage owns:

- ``connector.py``  — :class:`ApiConnector` subclass with classmethod
                      ``metadata()``. Auto-registers into
                      :data:`kaos_source.registry.default_api_registry`.
- ``client.py``     — raw async API functions (httpx-backed)
- ``models.py``     — frozen dataclass result types
- ``tools.py``      — MCP tool classes + ``register_<name>_tools``

Settings live separately under :mod:`kaos_source.settings.<name>`
(chunk 3 work).

Importing this package chain-imports all 5 API subpackages, which is
how the registry gets populated even when callers don't reach for the
tool layer (e.g. when an agent wants to introspect "which APIs are
available"). The 5 subpackages are independent — order does not matter.
"""

from __future__ import annotations

from kaos_source.apis import (
    ecfr,
    edgar,
    federal_register,
    gleif,
    govinfo,
)

__all__ = [
    "ecfr",
    "edgar",
    "federal_register",
    "gleif",
    "govinfo",
]
