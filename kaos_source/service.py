"""Back-compat shim. The real :class:`SourceService` lives in
:mod:`kaos_source.runtime.service` after Track 1 chunk 2.

Importing from this module continues to work
(``from kaos_source.service import SourceService``) — see
:mod:`kaos_source.runtime` for the runtime/ package and the chunk-2
notes in :mod:`kaos_source.runtime.service`.
"""

from __future__ import annotations

from kaos_source.runtime.service import (
    SourceOperationOptions,
    SourceOperationResult,
    SourceService,
)

__all__ = ["SourceOperationOptions", "SourceOperationResult", "SourceService"]
