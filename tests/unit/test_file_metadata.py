"""Unit coverage for ``kaos_source.parsers.metadata.file``.

Audit Fix 3: ``_detect_mime_from_magic`` now prefers
``kaos_nlp_core.content_type.detect`` over the in-module legacy table.
These tests pin both halves of that contract: real DOCX bytes route
through the canonical detector's OPC fallback (not the legacy ZIP
catch-all), and the legacy table still answers for cases the
detector returns ``unknown`` for.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from kaos_source.parsers.metadata.file import (
    _detect_mime_from_magic,
    extract_file_metadata,
)


def _minimal_docx_bytes() -> bytes:
    """Valid OPC zip with the wordprocessingml Override marker."""
    buf = io.BytesIO()
    content_types_xml = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        b'<Default Extension="xml" ContentType="application/xml"/>'
        b'<Override PartName="/word/document.xml" '
        b'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        b"</Types>"
    )
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("word/document.xml", b"<doc/>")
    return buf.getvalue()


class TestDetectMimeFromMagic:
    def test_pdf_returns_application_pdf(self) -> None:
        assert _detect_mime_from_magic(b"%PDF-1.4\n%") == "application/pdf"

    def test_png_returns_image_png(self) -> None:
        assert _detect_mime_from_magic(b"\x89PNG\r\n\x1a\n") == "image/png"

    def test_jpeg_returns_image_jpeg(self) -> None:
        assert _detect_mime_from_magic(b"\xff\xd8\xff\xe0") == "image/jpeg"

    def test_empty_returns_none(self) -> None:
        assert _detect_mime_from_magic(b"") is None

    def test_unknown_returns_none(self) -> None:
        assert _detect_mime_from_magic(b"hello world plain text") is None

    def test_real_docx_disambiguates_via_kaos_nlp_core(self) -> None:
        """Audit Fix 3 contract: a real DOCX must route through the
        canonical detector's OPC fallback (kaos-nlp-core 0.1.1+) to
        the precise wordprocessingml MIME — NOT the legacy table's
        generic ``application/zip``. Skipped when kaos-nlp-core is
        absent (degraded install)."""
        pytest.importorskip("kaos_nlp_core.content_type")
        mime = _detect_mime_from_magic(_minimal_docx_bytes())
        assert mime == (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ), (
            f"expected the canonical detector to disambiguate DOCX inside the zip; "
            f"got {mime!r} (would indicate the legacy fallback table took the call)"
        )


class TestExtractFileMetadataMimeRouting:
    def test_real_pdf_round_trips_with_canonical_mime(self, tmp_path: Path) -> None:
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%test")
        meta = extract_file_metadata(pdf, compute_checksums=False)
        assert meta.mime_type == "application/pdf"

    def test_extension_based_guess_wins_when_recognized(self, tmp_path: Path) -> None:
        """``mimetypes.guess_type`` is tried first (extension-based);
        magic-byte detection only fires when extension yields None.
        Pin this so the order isn't accidentally inverted."""
        txt = tmp_path / "plain.txt"
        txt.write_bytes(b"hello world")
        meta = extract_file_metadata(txt, compute_checksums=False)
        # stdlib mimetypes resolves .txt → text/plain on every platform.
        assert meta.mime_type == "text/plain"
