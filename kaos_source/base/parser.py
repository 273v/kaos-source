"""SourceParser — ABC for byte-stream parsers (vCard, EML, MBOX, EXIF, PACER).

Today's parsers in :mod:`kaos_source.parsers` are loose function
modules — :func:`parse_vcard`, :func:`parse_eml`, :func:`parse_pacer_docket`
— each called from a sibling ``tools_*.py`` file. Chunk 6 of Track 1
formalizes them into :class:`SourceParser` subclasses with explicit
:class:`ParserMetadata` declaring supported MIME types and extensions,
auto-registered into :class:`ParserRegistry` (chunk 4).

Why an ABC with a property + classmethod (and not a single ``parse()``
method as the abstract):

- Each parser returns a different result type (``list[VCardModel]`` for
  vCard, an envelope ``dict`` for EML, a ``PacerDocket`` model for
  PACER). Forcing a unified ``ParseResult`` either loses typing or
  forces every call site through ``Any``.
- The abstract surface here is just *identity* + *what we accept*:
  :meth:`metadata` (classmethod, defaulted) and
  :attr:`supported_mime_types` (property, abstract). The actual parse
  method is an implementation detail per subclass — consumers use
  :class:`ParserRegistry` to find the right parser, then call the
  parser's typed method directly.

Subclasses that want to advertise a structural ``parse()`` shape can
inherit (or just structurally satisfy) the corresponding Protocol in
:mod:`kaos_source.base.protocols` (e.g. ``ParsesBytes`` if/when added).

Type discipline mirrors :class:`SourceConnector` and
:class:`ApiConnector`: classmethod metadata, frozen pydantic identity
record.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from kaos_source.base.metadata import ParserMetadata

_CAMEL_TO_UNDERSCORE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _default_parser_name(cls: type) -> str:
    """Snake-cased class name as the default parser discriminator.

    ``VCardParser`` -> ``v_card_parser``; ``EmlParser`` -> ``eml_parser``.
    Strips leading underscores so private/test subclasses still produce
    a valid :attr:`ParserMetadata.name`.
    """
    name = cls.__name__.lstrip("_")
    return _CAMEL_TO_UNDERSCORE.sub("_", name).lower() if name else "parser"


def _first_doc_line(cls: type) -> str:
    """First non-empty line of a class's docstring, or fallback."""
    doc = cls.__doc__ or ""
    for line in doc.strip().splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return "(no description)"


class SourceParser(ABC):
    """ABC for any class that decodes a raw byte stream into typed records.

    Subclasses declare which MIME types they handle (used by
    :class:`ParserRegistry` for routing) and expose a parse method
    whose signature and return type they choose.

    The default :meth:`metadata` builds a :class:`ParserMetadata` from
    the class name + first line of ``__doc__``, with empty
    ``supported_mime_types`` and ``supported_extensions`` (subclasses
    must override to participate in registry routing).
    """

    @classmethod
    def metadata(cls) -> ParserMetadata:
        """Frozen identity record for this parser class.

        Subclasses override to set ``supported_mime_types``,
        ``supported_extensions``, ``capabilities``, ``tags``. Default
        builds from snake-cased class name + ``__doc__``.
        """
        return ParserMetadata(
            name=_default_parser_name(cls),
            description=_first_doc_line(cls),
        )

    @property
    @abstractmethod
    def supported_mime_types(self) -> tuple[str, ...]:
        """MIME types this parser can decode.

        Used by :class:`ParserRegistry` for content-type-based routing
        when a caller has bytes but no extension hint. Concrete parsers
        usually mirror this from their :meth:`metadata`'s
        ``supported_mime_types`` tuple to keep one source of truth.
        """
        ...


__all__ = ["SourceParser"]
