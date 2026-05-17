"""Internal adapter for routing file-input tools through ``kaos_core.path_resolver``.

Every MCP tool in ``kaos-source`` that accepts a ``path`` parameter from
agent input MUST route through :func:`resolve_source_input` (a thin
wrapper around :func:`kaos_core.path_resolver.resolve_input_path`)
instead of calling raw ``Path(p).exists()``. Without this, files
uploaded into ``KaosRuntime.vfs`` by a UI host (e.g. ``kaos-ui``'s
single-user-chat SPA) are invisible to tools — the agent then sees an
unbroken sequence of "File not found" errors and is at risk of
hallucinating answers from zero successful reads (see the
``vfs-blind-tools-audit-and-fix-plan`` in ``kaos-modules/docs/plans``
for the production post-mortem).

The wrapper exists so that:

1. kaos-source tools have a single place to apply package-wide
   defaults (no per-format mime restriction by default — kaos-source
   tools accept many shapes: EML, MBOX, vCard, JPEG, generic binary,
   archives, PACER HTML, etc.).
2. Tools that need a real mime gate (e.g. ``ParseEmlTool`` wanting
   ``message/rfc822``) pass an explicit ``allowed_mime_types`` tuple
   and inherit the rest of the resolver's contract (artifact / VFS /
   absolute filesystem resolution, cleanup, agent-friendly errors).
3. Callers without a ``KaosContext`` (CLI / tests) get a synthetic
   one so the resolver's filesystem fallback still works.

Usage::

    try:
        async with resolve_source_input(inputs.get("path", ""), context) as resolved:
            # everything that used `path` now uses `resolved.path`
            ...
    except InputPathResolutionError as exc:
        return ToolResult.create_error(exc.to_agent_message())
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from kaos_core.base.context import KaosContext
from kaos_core.path_resolver import (
    InputPathResolutionError,
    ResolvedInput,
    ResolvedOrigin,
    resolve_input_path,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@asynccontextmanager
async def resolve_source_input(
    path_or_uri: str,
    context: KaosContext | None,
    *,
    allowed_mime_types: tuple[str, ...] | None = None,
) -> AsyncIterator[ResolvedInput]:
    """Resolve an agent-supplied path/URI to a real on-disk path.

    Adapter wrapping :func:`kaos_core.path_resolver.resolve_input_path`
    with no per-format mime restriction by default — kaos-source tools
    accept many shapes (EML, MBOX, vCard, JPEG, generic binary,
    archives, etc.).

    Pass ``allowed_mime_types`` only when the tool genuinely needs to
    gate on type (e.g. :class:`ParseEmlTool` wants ``message/rfc822``).
    Be conservative: when in doubt, leave it ``None``. The actual
    parser will fail with a clearer message on wrong content than a
    mime guard ever could.

    When ``context`` is ``None`` (CLI / direct API calls) the resolver
    is given a synthetic ``KaosContext(session_id="cli")`` so the
    filesystem-fallback branch still works for absolute paths.
    """
    ctx = context if context is not None else KaosContext(session_id="cli")
    async with resolve_input_path(
        path_or_uri,
        context=ctx,
        allowed_mime_types=allowed_mime_types,
    ) as resolved:
        yield resolved


__all__ = [
    "InputPathResolutionError",
    "ResolvedInput",
    "ResolvedOrigin",
    "resolve_source_input",
]
