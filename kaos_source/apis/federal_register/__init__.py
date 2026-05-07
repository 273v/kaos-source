"""Federal Register API subpackage.

Layout:

- :mod:`.models` — frozen dataclasses (FRDocument, FRSearchResult, FRAgency)
- :mod:`.client` — raw async functions (search_documents, get_document, ...)
- :mod:`.connector` — :class:`FederalRegisterApiConnector` (metadata-only for chunk 5)
- :mod:`.tools` — MCP tool classes + ``register_federal_register_tools(runtime)``

Importing this subpackage auto-registers
:class:`FederalRegisterApiConnector` into
:data:`kaos_source.registry.default_api_registry` under the name
``federal_register``.
"""

from __future__ import annotations

from kaos_source.apis.federal_register.connector import FederalRegisterApiConnector
from kaos_source.apis.federal_register.tools import register_federal_register_tools
from kaos_source.registry import default_api_registry
from kaos_source.settings.federal_register import KaosSourceFRSettings

default_api_registry.register("federal_register", FederalRegisterApiConnector, force=True)

__all__ = [
    "FederalRegisterApiConnector",
    "KaosSourceFRSettings",
    "register_federal_register_tools",
]
