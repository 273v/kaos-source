"""Back-compat shim — FR MCP tools moved to ``kaos_source.apis.federal_register.tools``.

Track 1 chunk 5 reorganized data-API connectors and tools under
:mod:`kaos_source.apis`. This module re-exports the FR tool surface so
existing imports keep resolving::

    from kaos_source.tools_federal_register import (
        FRSearchTool, FRGetDocumentTool, FRGetContentTool, FRAgenciesTool,
        register_federal_register_tools,
    )

New code should import from :mod:`kaos_source.apis.federal_register.tools`.
"""

from __future__ import annotations

from kaos_source.apis.federal_register.tools import (  # noqa: F401
    FRAgenciesTool,
    FRGetContentTool,
    FRGetDocumentTool,
    FRSearchTool,
    register_federal_register_tools,
)
