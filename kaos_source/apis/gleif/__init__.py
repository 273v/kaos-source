"""GLEIF (Global Legal Entity Identifier) API package.

Public REST API at ``api.gleif.org/api/v1`` — no authentication required.
Returns structured legal entity records: LEI code, legal name,
jurisdiction, registered/HQ addresses, entity status, registration
authority. Covers ~2.5M entities globally.

Layout (mirrors the other ``kaos_source.apis.*`` subpackages):

- :mod:`.models`    — frozen dataclass value types (:class:`LEIEntity`,
  :class:`LEIAddress`)
- :mod:`.client`    — raw async HTTP functions (:func:`search_lei`,
  :func:`search_lei_by_country`, :func:`get_lei`)
- :mod:`.connector` — :class:`GleifApiConnector` (:class:`ApiConnector`
  subclass; carries metadata for the registry)
- :mod:`.tools`     — MCP tool classes plus
  :func:`register_gleif_tools`

Importing this package auto-registers :class:`GleifApiConnector` into
:data:`kaos_source.registry.default_api_registry` under the name
``"gleif"``.

Unlike the other apis subpackages, GLEIF has *no* dedicated settings
class — the API is unauthenticated and the only knob is a per-call
``timeout`` parameter on each client function.
"""

from __future__ import annotations

from kaos_source.apis.gleif.connector import GleifApiConnector
from kaos_source.apis.gleif.tools import register_gleif_tools
from kaos_source.registry import default_api_registry

default_api_registry.register("gleif", GleifApiConnector, force=True)

__all__ = [
    "GleifApiConnector",
    "register_gleif_tools",
]
