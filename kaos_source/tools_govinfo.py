"""Back-compat shim — moved to :mod:`kaos_source.apis.govinfo.tools`.

GovInfo MCP tool classes and :func:`register_govinfo_tools` now live in
:mod:`kaos_source.apis.govinfo.tools`. Existing imports of
``kaos_source.tools_govinfo`` continue to resolve via this shim — prefer
the new location for new code.
"""

from __future__ import annotations

from kaos_source.apis.govinfo.tools import (
    GovInfoCollectionsTool,
    GovInfoGetPackageTool,
    GovInfoSearchTool,
    register_govinfo_tools,
)

__all__ = [
    "GovInfoCollectionsTool",
    "GovInfoGetPackageTool",
    "GovInfoSearchTool",
    "register_govinfo_tools",
]
