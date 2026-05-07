"""Byte-stream parsers — :class:`SourceParser` implementations.

Track 1 chunk 6 added the :class:`SourceParser` ABC layer (defined in
:mod:`kaos_source.base.parser`) and clustered email parsers under
:mod:`kaos_source.parsers.email`. Importing this package auto-registers
all 6 builtin parsers into
:data:`kaos_source.registry.default_parser_registry` with ``force=True``
so module re-imports stay idempotent.

Parsers (6 total):

- :class:`VCardParser`         — RFC 6350/2426/2.1 vCard
                                 (``text/vcard`` / ``text/x-vcard``)
- :class:`EmlParser`           — RFC 5322 / MIME email
                                 (``message/rfc822``)
- :class:`MboxParser`          — Berkeley mbox archive
                                 (``application/mbox``)
- :class:`PacerParser`         — PACER docket HTML (no MIME index entry —
                                 conflicts with generic HTML; discover by name)
- :class:`FileMetadataParser`  — generic file metadata (no MIME index entry —
                                 accepts any file; discover by name)
- :class:`ImageMetadataParser` — EXIF + GPS from JPEG/TIFF/PNG/WebP

Out-of-tree custom parsers register explicitly::

    from kaos_source.registry import default_parser_registry
    default_parser_registry.register("my_parser", MyParser, force=True)
"""

from __future__ import annotations

from kaos_source.parsers.email.eml import EmlParser
from kaos_source.parsers.email.mbox import MboxParser
from kaos_source.parsers.file_meta import FileMetadataParser
from kaos_source.parsers.image_meta import ImageMetadataParser
from kaos_source.parsers.pacer.parser import PacerParser
from kaos_source.parsers.vcard.parser import VCardParser
from kaos_source.registry.parser_registry import default_parser_registry

# Auto-register the 6 built-in parsers. ``force=True`` makes module
# re-imports idempotent (e.g. during pytest collection across multiple
# test sessions).
default_parser_registry.register("vcard", VCardParser, force=True)
default_parser_registry.register("eml", EmlParser, force=True)
default_parser_registry.register("mbox", MboxParser, force=True)
default_parser_registry.register("pacer_docket", PacerParser, force=True)
default_parser_registry.register("file_metadata", FileMetadataParser, force=True)
default_parser_registry.register("image_metadata", ImageMetadataParser, force=True)


__all__ = [
    "EmlParser",
    "FileMetadataParser",
    "ImageMetadataParser",
    "MboxParser",
    "PacerParser",
    "VCardParser",
]
