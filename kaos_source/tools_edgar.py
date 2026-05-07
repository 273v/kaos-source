"""Back-compat shim — EDGAR MCP tools moved to ``kaos_source.apis.edgar.tools``.

Track 1 chunk 5 reorganized data-API connectors and tools under
:mod:`kaos_source.apis`. This module re-exports the EDGAR tool surface
so existing imports keep resolving::

    from kaos_source.tools_edgar import (
        EdgarSearchTool, EdgarCompanyTool, EdgarLookupTool,
        register_edgar_tools,
    )

New code should import from :mod:`kaos_source.apis.edgar.tools`.
"""

from __future__ import annotations

from kaos_source.apis.edgar.tools import (  # noqa: F401
    EdgarCompanyTool,
    EdgarLookupTool,
    EdgarSearchTool,
    register_edgar_tools,
)
