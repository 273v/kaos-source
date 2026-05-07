"""Decode raw preview bytes into a :class:`SourcePreview`.

Auto-detects text vs. binary by:

1. MIME type (``text/*`` and the structured-text JSON/XML/YAML types are text)
2. Absence of NUL bytes in the first chunk (heuristic for text-without-MIME)

Text payloads are decoded with the requested encoding (replacement on
errors); binary payloads are returned via :meth:`SourcePreview.from_binary`
with a base64 inline body.
"""

from __future__ import annotations

from kaos_source.models import SourcePreview


def decode_preview_payload(
    payload: bytes,
    *,
    source_id: str,
    size: int | None,
    mime_type: str | None,
    encoding: str,
    truncated_override: bool | None = None,
) -> SourcePreview:
    """Build a :class:`SourcePreview` from raw bytes."""
    truncated = (
        truncated_override
        if truncated_override is not None
        else (size is not None and size > len(payload))
    )
    is_text = False
    if mime_type is not None:
        is_text = mime_type.startswith("text/") or mime_type in {
            "application/json",
            "application/xml",
            "application/yaml",
        }
    if not is_text and b"\x00" not in payload:
        is_text = True
    if is_text:
        return SourcePreview(
            source_id=source_id,
            text_preview=payload.decode(encoding, errors="replace"),
            truncated=truncated,
            size=size,
            mime_type=mime_type,
        )
    return SourcePreview.from_binary(
        source_id=source_id,
        payload=payload,
        truncated=truncated,
        size=size,
        mime_type=mime_type,
    )
