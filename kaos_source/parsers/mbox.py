"""Back-compat shim — moved to :mod:`kaos_source.parsers.email.mbox` in
Track 1 chunk 6.

Existing ``from kaos_source.parsers.mbox import ...`` callers continue
to resolve via the re-exports below. Prefer the new location for new
code:

    from kaos_source.parsers.email.mbox import parse_mbox, MboxResult
"""

from __future__ import annotations

from kaos_source.parsers.email.mbox import (  # noqa: F401
    MboxParser,
    MboxResult,
    parse_mbox,
)
