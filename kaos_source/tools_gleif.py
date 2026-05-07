"""Backwards-compatibility shim — GLEIF MCP tools moved to :mod:`kaos_source.apis.gleif.tools`.

New code should import from :mod:`kaos_source.apis.gleif.tools` (or the
``kaos_source.apis.gleif`` package re-export). This shim re-exports
:func:`register_gleif_tools` so existing
``from kaos_source.tools_gleif import register_gleif_tools`` imports
keep working.
"""

from __future__ import annotations

from kaos_source.apis.gleif.tools import (
    GleifGetTool,
    GleifSearchTool,
    register_gleif_tools,
)

__all__ = [
    "GleifGetTool",
    "GleifSearchTool",
    "register_gleif_tools",
]
