"""PACER docket HTML parser — local, no network, no auth.

Track 1 chunk 8d moved this from a single ``parsers/pacer.py`` file
into a focused subpackage so the parsing logic and its MCP tool layer
live together (mirroring ``parsers/vcard/`` and each ``apis/<X>/``).

Layout:

- :mod:`.parser` — :func:`parse_docket` plus dataclass models
                   (:class:`DocketInfo`, :class:`DocketEntry`,
                   :class:`FilingInfo`, :class:`DocumentLink`) and the
                   :class:`PacerParser` :class:`SourceParser` subclass
- :mod:`.tools`  — :class:`PacerParseDocketTool`,
                   :class:`PacerFilterEntriesTool`, and
                   :func:`register_pacer_tools`
"""

from __future__ import annotations

from kaos_source.parsers.pacer.parser import (
    DocketEntry,
    DocketInfo,
    DocumentLink,
    FilingInfo,
    PacerParser,
    parse_docket,
)
from kaos_source.parsers.pacer.tools import (
    PacerFilterEntriesTool,
    PacerParseDocketTool,
    register_pacer_tools,
)

__all__ = [
    "DocketEntry",
    "DocketInfo",
    "DocumentLink",
    "FilingInfo",
    "PacerFilterEntriesTool",
    "PacerParseDocketTool",
    "PacerParser",
    "parse_docket",
    "register_pacer_tools",
]
