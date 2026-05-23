"""Generic file metadata extraction — pure stdlib, no external deps.

Extracts filesystem metadata (timestamps, size), MIME type detection,
and cryptographic checksums (MD5, SHA-256, BLAKE2b).
"""

from __future__ import annotations

import hashlib
import mimetypes
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")


class FileMetadata(BaseModel):
    """File-level metadata."""

    model_config = _STRICT

    path: str
    name: str
    extension: str | None = None
    size_bytes: int
    mime_type: str | None = None
    created_at: str | None = Field(None, description="ISO 8601")
    modified_at: str | None = Field(None, description="ISO 8601")
    accessed_at: str | None = Field(None, description="ISO 8601")
    md5: str | None = None
    sha256: str | None = None
    blake2b: str | None = None
    is_binary: bool | None = Field(None, description="True if file appears binary")
    magic_bytes: str | None = Field(None, description="First 8 bytes as hex")


# ── Magic bytes → format mapping ────────────────────────────────────
#
# Audit Fix 3: the canonical magic-byte detector lives in
# ``kaos_nlp_core.content_type``; that module's 0.1.1+ release adds an
# OPC + OLE fallback that correctly disambiguates real DOCX / PPTX /
# XLSX / DOC / XLS / PPT — coverage this in-module ``_MAGIC_SIGNATURES``
# table cannot match.
#
# We prefer the canonical detector when ``kaos-nlp-core`` is on the
# path (the kaos-source default install already pulls it in via the
# package's main dependency line). The in-module fallback table
# remains so the function stays callable in degraded installs that
# somehow lack kaos-nlp-core (e.g. partial dependency overrides) —
# narrower coverage but no crash.
#
# Tracked in
# ``kaos-modules/docs/audits/2026-05-22-content-type-detection-unused.md``
# Fix 3.

_MAGIC_SIGNATURES: list[tuple[bytes, str]] = [
    (b"%PDF", "application/pdf"),
    (b"\x89PNG", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"PK\x03\x04", "application/zip"),
    (b"PK\x05\x06", "application/zip"),
    (b"Rar!", "application/x-rar-compressed"),
    (b"\x1f\x8b", "application/gzip"),
    (b"BZ", "application/x-bzip2"),
    (b"\xfd7zXZ", "application/x-xz"),
    (b"7z\xbc\xaf", "application/x-7z-compressed"),
    (b"\x00\x00\x00\x1cftyp", "video/mp4"),
    (b"\xd0\xcf\x11\xe0", "application/x-ole-storage"),  # OLE: .doc, .xls, .msg
    (b"RIFF", "application/octet-stream"),  # WAV, AVI, WebP (needs further check)
    (b"\x50\x4b\x03\x04", "application/zip"),  # Also DOCX, XLSX, PPTX (OPC)
]


def _detect_mime_from_magic(header: bytes) -> str | None:
    """Detect MIME type from magic bytes.

    Prefers the canonical ``kaos_nlp_core.content_type.detect`` detector
    (0.1.1+ ships an OPC + OLE fallback that distinguishes real DOCX /
    PPTX / XLSX / DOC / XLS / PPT bytes — coverage the legacy fallback
    table here cannot match). Falls back to the in-module
    ``_MAGIC_SIGNATURES`` table when kaos-nlp-core is unavailable at
    runtime (degraded install) or when its detector returns ``unknown``
    for bytes the table happens to recognize.
    """
    if not header:
        return None

    try:
        from kaos_nlp_core.content_type import detect
    except ImportError:
        # kaos-nlp-core unavailable — fall through to the legacy table.
        pass
    else:
        result = detect(header)
        if result.mime_type:
            return result.mime_type
        # Detector returned group="unknown" — try the legacy table on
        # the chance it recognizes something infer doesn't.

    for magic, mime in _MAGIC_SIGNATURES:
        if header.startswith(magic):
            return mime
    return None


def _is_binary(header: bytes) -> bool:
    """Heuristic: file is binary if it contains null bytes in first 8KB."""
    return b"\x00" in header


def _timestamp_to_iso(ts: float) -> str:
    """Convert Unix timestamp to ISO 8601."""
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


# ── Main extraction ─────────────────────────────────────────────────


def extract_file_metadata(
    path: str | Path,
    *,
    compute_checksums: bool = True,
    checksum_algorithms: tuple[str, ...] = ("md5", "sha256"),
) -> FileMetadata:
    """Extract metadata for a file on disk.

    Args:
        path: Path to the file.
        compute_checksums: Whether to compute hash digests.
        checksum_algorithms: Which algorithms to use (md5, sha256, blake2b).

    Returns:
        FileMetadata with all available fields.
    """
    p = Path(path).resolve()
    stat = p.stat()

    # Extension
    ext = p.suffix.lower() if p.suffix else None

    # MIME type (from extension)
    mime, _ = mimetypes.guess_type(str(p))

    # Read first 8KB for magic bytes and binary detection
    with p.open("rb") as f:
        header = f.read(8192)

    magic_hex = header[:8].hex() if header else None
    binary = _is_binary(header) if header else None

    # Override MIME from magic bytes if extension-based guess failed
    if not mime and header:
        mime = _detect_mime_from_magic(header)

    # Checksums
    md5_hash: str | None = None
    sha256_hash: str | None = None
    blake2b_hash: str | None = None

    if compute_checksums:
        hashers: dict[str, hashlib._Hash] = {}
        if "md5" in checksum_algorithms:
            # MD5 is offered for eDiscovery tool compat only (SHA-256 +
            # BLAKE2b are the integrity-bearing checksums). ``usedforsecurity=False``
            # documents the intent and keeps Bandit B324 quiet.
            hashers["md5"] = hashlib.md5(usedforsecurity=False)
        if "sha256" in checksum_algorithms:
            hashers["sha256"] = hashlib.sha256()
        if "blake2b" in checksum_algorithms:
            hashers["blake2b"] = hashlib.blake2b()  # type: ignore[assignment]  # ty: ignore[invalid-assignment]  # blake2b duck-types _Hash

        with p.open("rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                for h in hashers.values():
                    h.update(chunk)

        md5_hash = hashers["md5"].hexdigest() if "md5" in hashers else None
        sha256_hash = hashers["sha256"].hexdigest() if "sha256" in hashers else None
        blake2b_hash = hashers["blake2b"].hexdigest() if "blake2b" in hashers else None

    # Timestamps
    created_at = None
    if hasattr(stat, "st_birthtime"):
        created_at = _timestamp_to_iso(stat.st_birthtime)
    elif stat.st_ctime:
        created_at = _timestamp_to_iso(stat.st_ctime)

    return FileMetadata(
        path=str(p),
        name=p.name,
        extension=ext,
        size_bytes=stat.st_size,
        mime_type=mime,
        created_at=created_at,
        modified_at=_timestamp_to_iso(stat.st_mtime),
        accessed_at=_timestamp_to_iso(stat.st_atime),
        md5=md5_hash,
        sha256=sha256_hash,
        blake2b=blake2b_hash,
        is_binary=binary,
        magic_bytes=magic_hex,
    )


# ---------------------------------------------------------------------------
# SourceParser conformance (Track 1 chunk 6)
# ---------------------------------------------------------------------------

from kaos_source.base.capabilities import SourceCapability  # noqa: E402
from kaos_source.base.metadata import ParserMetadata  # noqa: E402
from kaos_source.base.parser import SourceParser  # noqa: E402


class FileMetadataParser(SourceParser):
    """:class:`SourceParser` wrapper for :func:`extract_file_metadata`.

    Generic file metadata extractor — size, timestamps, MIME (via
    :mod:`mimetypes` + magic bytes), MD5/SHA-256/BLAKE2b checksums.
    Accepts any file; no MIME-type narrowing, so the parser is
    discovered by name rather than via the MIME secondary index.
    """

    @classmethod
    def metadata(cls) -> ParserMetadata:
        return ParserMetadata(
            name="file_metadata",
            description="Generic file metadata: size, timestamps, MIME, MD5/SHA-256/BLAKE2b.",
            supported_mime_types=(),
            supported_extensions=(),
            capabilities=(SourceCapability.PARSE,),
        )

    @property
    def supported_mime_types(self) -> tuple[str, ...]:
        return ()

    def parse(self, path: str | Path) -> FileMetadata:
        return extract_file_metadata(path)
