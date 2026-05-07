"""Back-compat shim for the eCFR MCP tools.

The canonical implementation moved to :mod:`kaos_source.apis.ecfr.tools`
in Track 1 chunk 5. This module preserves the legacy import path
``from kaos_source.tools_ecfr import register_ecfr_tools`` so existing
callers (the package ``__init__`` and ``register_source_tools``) keep
resolving without changes.
"""

from __future__ import annotations

from kaos_source.apis.ecfr.tools import (
    ECFRContentTool,
    ECFRListTitlesTool,
    ECFRSearchTool,
    ECFRStructureTool,
    register_ecfr_tools,
)

__all__ = [
    "ECFRContentTool",
    "ECFRListTitlesTool",
    "ECFRSearchTool",
    "ECFRStructureTool",
    "register_ecfr_tools",
]
