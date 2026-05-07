"""MIME-type guessing — single-purpose wrapper over :mod:`mimetypes`."""

from __future__ import annotations

import mimetypes


def guess_mime_type(name: str, fallback: str | None = None) -> str | None:
    """Best-effort MIME type for a filename, with optional fallback."""
    mime_type, _ = mimetypes.guess_type(name)
    return mime_type or fallback
