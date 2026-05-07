"""Filesystem + image metadata parsers — extraction without parsing the body.

Track 1 chunk 8e clusters the two byte-stream metadata parsers here so
their parsers + MCP tools live together (mirroring ``parsers/email/``
and ``parsers/{vcard,pacer}/``).

Layout:

- :mod:`.file`   — :func:`extract_file_metadata` plus :class:`FileMetadata`
                   pydantic model + :class:`FileMetadataParser`
                   :class:`SourceParser` subclass; size, timestamps,
                   MIME via :mod:`mimetypes`+magic-bytes, MD5/SHA-256/
                   BLAKE2b checksums
- :mod:`.image`  — :func:`extract_image_metadata` plus :class:`ImageMetadata`
                   pydantic model + :class:`ImageMetadataParser`;
                   EXIF + GPS extraction from JPEG/TIFF/PNG/WebP via
                   Pillow
- :mod:`.tools`  — :class:`FileMetadataTool` + :class:`ImageMetadataTool`
                   MCP tool classes plus :func:`register_metadata_tools`
"""

from __future__ import annotations

from kaos_source.parsers.metadata.file import (
    FileMetadata,
    FileMetadataParser,
    extract_file_metadata,
)
from kaos_source.parsers.metadata.image import (
    GpsCoordinates,
    ImageMetadata,
    ImageMetadataParser,
    extract_image_metadata,
)
from kaos_source.parsers.metadata.tools import (
    FileMetadataTool,
    ImageMetadataTool,
    register_metadata_tools,
)

__all__ = [
    "FileMetadata",
    "FileMetadataParser",
    "FileMetadataTool",
    "GpsCoordinates",
    "ImageMetadata",
    "ImageMetadataParser",
    "ImageMetadataTool",
    "extract_file_metadata",
    "extract_image_metadata",
    "register_metadata_tools",
]
