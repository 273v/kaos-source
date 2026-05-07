"""vCard parser — RFC 6350 (4.0), RFC 2426 (3.0), and 2.1 with quoted-printable.

Track 1 chunk 8c moved this from a single ``parsers/vcard.py`` file into
a focused subpackage so the parsing logic and its MCP tool layer live
together (mirroring how each ``apis/<X>/`` subpackage holds its own
``client.py`` + ``tools.py``).

Layout:

- :mod:`.parser` — :func:`parse_vcard` plus all dataclass models
                   (:class:`VCardModel`, :class:`VCardName`, etc.) and
                   the :class:`VCardParser` :class:`SourceParser`
                   subclass
- :mod:`.tools`  — :class:`VCardParseTool` MCP tool +
                   :func:`register_vcard_tools`
"""

from __future__ import annotations

from kaos_source.parsers.vcard.parser import (
    AddressType,
    EmailType,
    TelephoneType,
    VCardAddress,
    VCardEmail,
    VCardGender,
    VCardImage,
    VCardModel,
    VCardName,
    VCardOrganization,
    VCardParser,
    VCardParseStatus,
    VCardProperty,
    VCardSocialProfile,
    VCardTelephone,
    VCardVersion,
    parse_property_line,
    parse_vcard,
    unfold_lines,
)
from kaos_source.parsers.vcard.tools import (
    VCardParseTool,
    register_vcard_tools,
)

__all__ = [
    "AddressType",
    "EmailType",
    "TelephoneType",
    "VCardAddress",
    "VCardEmail",
    "VCardGender",
    "VCardImage",
    "VCardModel",
    "VCardName",
    "VCardOrganization",
    "VCardParseStatus",
    "VCardParseTool",
    "VCardParser",
    "VCardProperty",
    "VCardSocialProfile",
    "VCardTelephone",
    "VCardVersion",
    "parse_property_line",
    "parse_vcard",
    "register_vcard_tools",
    "unfold_lines",
]
