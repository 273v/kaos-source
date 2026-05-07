"""Electronic Code of Federal Regulations (eCFR) public REST API.

Subpackage layout (Track 1 chunk 5):

- :mod:`.models` — typed dataclasses for API responses
- :mod:`.client` — raw async functions (httpx-backed) keyed off
  :class:`KaosSourceECFRSettings`
- :mod:`.connector` — :class:`ECFRApiConnector` ABC subclass
  (:meth:`metadata` only for chunk 5; capability methods follow later)
- :mod:`.tools` — MCP tool classes + ``register_ecfr_tools(runtime)``

Importing this subpackage auto-registers
:class:`ECFRApiConnector` into
:data:`kaos_source.registry.default_api_registry` under the name
``"ecfr"``.
"""

from __future__ import annotations

from kaos_source.apis.ecfr.client import (
    get_agencies,
    get_latest_date,
    get_section_content,
    get_title_structure,
    get_titles,
)
from kaos_source.apis.ecfr.connector import ECFRApiConnector
from kaos_source.apis.ecfr.models import ECFRAgency, ECFRStructureNode, ECFRTitle
from kaos_source.apis.ecfr.tools import (
    ECFRContentTool,
    ECFRListTitlesTool,
    ECFRSearchTool,
    ECFRStructureTool,
    register_ecfr_tools,
)
from kaos_source.registry import default_api_registry
from kaos_source.settings.ecfr import KaosSourceECFRSettings

# Auto-register the eCFR api connector class so the registry is
# populated on import. ``force=True`` makes module re-imports
# idempotent (e.g. during pytest collection with multiple test sessions).
default_api_registry.register("ecfr", ECFRApiConnector, force=True)


__all__ = [
    "ECFRAgency",
    "ECFRApiConnector",
    "ECFRContentTool",
    "ECFRListTitlesTool",
    "ECFRSearchTool",
    "ECFRStructureNode",
    "ECFRStructureTool",
    "ECFRTitle",
    "KaosSourceECFRSettings",
    "get_agencies",
    "get_latest_date",
    "get_section_content",
    "get_title_structure",
    "get_titles",
    "register_ecfr_tools",
]
