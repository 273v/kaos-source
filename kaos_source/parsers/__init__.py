"""Byte-stream parsers — :class:`SourceParser` implementations.

Track 1 chunk 6 added the :class:`SourceParser` ABC layer (defined in
:mod:`kaos_source.base.parser`) and clustered email parsers under
:mod:`kaos_source.parsers.email`. Importing this package auto-registers
all 6 builtin parsers into
:data:`kaos_source.registry.default_parser_registry` with ``force=True``
so module re-imports stay idempotent.

Track 1 chunks 8c-8e completed the cohesive layout: vcard, pacer, and
metadata each became their own subpackage holding parser + models +
MCP tools side-by-side, and the legacy ``kaos_source/tools_forensics.py``
was dissolved into :mod:`.email.tools` (3 email tools) +
:mod:`.metadata.tools` (2 metadata tools), bridged here by
:func:`register_forensics_tools` for back-compat.

Parsers (6 total) and the subpackage that owns each:

- :class:`VCardParser`         — :mod:`.vcard.parser`
                                 (``text/vcard`` / ``text/x-vcard``)
- :class:`EmlParser`           — :mod:`.email.eml` (``message/rfc822``)
- :class:`MboxParser`          — :mod:`.email.mbox` (``application/mbox``)
- :class:`PacerParser`         — :mod:`.pacer.parser` (no MIME index —
                                 conflicts with generic HTML; discover by name)
- :class:`FileMetadataParser`  — :mod:`.metadata.file` (no MIME index —
                                 accepts any file; discover by name)
- :class:`ImageMetadataParser` — :mod:`.metadata.image`
                                 (image/jpeg, tiff, png, webp)

Out-of-tree custom parsers register explicitly::

    from kaos_source.registry import default_parser_registry
    default_parser_registry.register("my_parser", MyParser, force=True)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kaos_source.parsers.email.eml import EmlParser
from kaos_source.parsers.email.mbox import MboxParser
from kaos_source.parsers.email.tools import register_email_tools
from kaos_source.parsers.metadata.file import FileMetadataParser
from kaos_source.parsers.metadata.image import ImageMetadataParser
from kaos_source.parsers.metadata.tools import register_metadata_tools
from kaos_source.parsers.pacer.parser import PacerParser
from kaos_source.parsers.vcard.parser import VCardParser
from kaos_source.registry.parser_registry import default_parser_registry

if TYPE_CHECKING:
    from kaos_core import KaosRuntime

# Auto-register the 6 built-in parsers. ``force=True`` makes module
# re-imports idempotent (e.g. during pytest collection across multiple
# test sessions).
default_parser_registry.register("vcard", VCardParser, force=True)
default_parser_registry.register("eml", EmlParser, force=True)
default_parser_registry.register("mbox", MboxParser, force=True)
default_parser_registry.register("pacer_docket", PacerParser, force=True)
default_parser_registry.register("file_metadata", FileMetadataParser, force=True)
default_parser_registry.register("image_metadata", ImageMetadataParser, force=True)


def register_forensics_tools(runtime: KaosRuntime) -> int:
    """Register the e-discovery / forensics MCP tool bundle.

    Convenience orchestrator that fans out to the per-parser-family
    register functions:

    - :func:`kaos_source.parsers.email.tools.register_email_tools` —
      ``kaos-source-parse-eml`` + ``kaos-source-parse-mbox`` +
      ``kaos-source-email-forensics`` (3 tools)
    - :func:`kaos_source.parsers.metadata.tools.register_metadata_tools` —
      ``kaos-source-image-metadata`` + ``kaos-source-file-metadata``
      (2 tools)

    Track 1 chunk 8e split the legacy ``tools_forensics.py`` into the
    above per-family files; this orchestrator preserves the original
    "register all 5 forensic tools" surface for callers that don't
    care about the email-vs-metadata cleavage.
    """
    count = register_email_tools(runtime)
    count += register_metadata_tools(runtime)
    return count


__all__ = [
    "EmlParser",
    "FileMetadataParser",
    "ImageMetadataParser",
    "MboxParser",
    "PacerParser",
    "VCardParser",
    "register_email_tools",
    "register_forensics_tools",
    "register_metadata_tools",
]
