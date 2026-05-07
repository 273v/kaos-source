"""SEC EDGAR API subpackage.

Layout:

- :mod:`.models` — frozen dataclasses (EdgarFiling, EdgarSearchResponse,
  EdgarCompany)
- :mod:`.client` — raw async functions (search_filings, get_company,
  lookup_ticker, fetch_filing_document, filing_html_to_document)
- :mod:`.connector` — :class:`EdgarApiConnector` (metadata-only for chunk 5)
- :mod:`.tools` — MCP tool classes + ``register_edgar_tools(runtime)``

Importing this subpackage auto-registers :class:`EdgarApiConnector` into
:data:`kaos_source.registry.default_api_registry` under the name
``edgar``.
"""

from __future__ import annotations

from kaos_source.apis.edgar.connector import EdgarApiConnector
from kaos_source.apis.edgar.tools import register_edgar_tools
from kaos_source.registry import default_api_registry
from kaos_source.settings.edgar import DEFAULT_EDGAR_USER_AGENT, KaosSourceEdgarSettings

default_api_registry.register("edgar", EdgarApiConnector, force=True)

__all__ = [
    "DEFAULT_EDGAR_USER_AGENT",
    "EdgarApiConnector",
    "KaosSourceEdgarSettings",
    "register_edgar_tools",
]
