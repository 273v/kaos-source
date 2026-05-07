"""Opaque pagination cursors for ``discover()`` results.

Cursors are urlsafe-base64 strings encoding ``offset:N``. The opaque
shape lets us evolve the encoding (e.g. add a section field) without
breaking clients that round-trip the cursor verbatim.
"""

from __future__ import annotations

import base64

from kaos_source.errors import SourceValidationError


def encode_cursor(offset: int) -> str:
    """Encode an integer offset as an opaque cursor string."""
    raw = f"offset:{offset}".encode()
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str | None) -> int:
    """Decode an opaque cursor back to its offset.

    Raises :class:`SourceValidationError` if the cursor is malformed —
    the agent-friendly message lets callers self-correct.
    """
    if cursor is None:
        return 0
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        prefix, value = decoded.split(":", 1)
    except Exception as exc:
        raise SourceValidationError("Invalid discovery cursor", cursor=cursor) from exc
    if prefix != "offset" or not value.isdigit():
        raise SourceValidationError("Invalid discovery cursor", cursor=cursor)
    return int(value)
