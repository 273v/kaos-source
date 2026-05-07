"""ParserRegistry — name → :class:`SourceParser` class, with MIME secondary index.

Mirrors :class:`kaos_agents.registry.pattern_registry.PatternRegistry`
shape but for byte-stream parsers. Holds *classes* (not instances) for
the same reasons as :class:`ApiRegistry` — parsers are typically cheap
to construct and may be parameterised differently per call.

Adds a secondary MIME-type index: when a caller has bytes and a
content-type hint but no parser name, :meth:`get_by_mime_type` resolves
to the registered parser whose
:attr:`ParserMetadata.supported_mime_types` contains that type.

Populated by :mod:`kaos_source.parsers` on import (Track 1 chunk 6).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kaos_core.exceptions import RegistryError

if TYPE_CHECKING:
    from kaos_source.base.parser import SourceParser


class ParserRegistry:
    """Catalogue of name → :class:`SourceParser` subclass.

    Lookup by name (primary) or by MIME type (secondary). The MIME
    index is rebuilt incrementally on every :meth:`register` /
    :meth:`unregister` call, so iteration order matches registration
    order.

    Typical use::

        from kaos_source.registry import default_parser_registry

        # By name
        cls = default_parser_registry.get("vcard")

        # By MIME type
        cls = default_parser_registry.get_by_mime_type("text/vcard")

        if cls is not None:
            records = cls().parse(payload)
    """

    __slots__ = ("_by_mime_type", "_by_name")

    def __init__(self) -> None:
        self._by_name: dict[str, type[SourceParser]] = {}
        self._by_mime_type: dict[str, type[SourceParser]] = {}

    # --- Mutation -----------------------------------------------------

    def register(
        self,
        name: str,
        cls: type[SourceParser],
        *,
        force: bool = False,
    ) -> None:
        """Register a parser class under ``name``.

        The class's :attr:`ParserMetadata.supported_mime_types` are also
        indexed for :meth:`get_by_mime_type` lookups. Conflicting MIME
        registrations from a different parser raise unless ``force``.

        Args:
            name: Parser discriminator (typically
                ``cls.metadata().name``).
            cls: A :class:`SourceParser` subclass.
            force: When ``True``, replaces any existing registration
                for this name AND any MIME conflicts.

        Raises:
            RegistryError: On name or MIME-type collision without ``force``.
        """
        existing = self._by_name.get(name)
        if existing is not None and existing is not cls and not force:
            raise RegistryError(
                "Parser already registered with this name",
                parser_name=name,
                existing=existing.__name__,
                attempted=cls.__name__,
            )
        self._by_name[name] = cls

        meta = cls.metadata()
        for mime_type in meta.supported_mime_types:
            mime_existing = self._by_mime_type.get(mime_type)
            if mime_existing is not None and mime_existing is not cls and not force:
                raise RegistryError(
                    "Parser already registered for this MIME type",
                    mime_type=mime_type,
                    existing=mime_existing.__name__,
                    attempted=cls.__name__,
                )
            self._by_mime_type[mime_type] = cls

    def unregister(self, name: str) -> type[SourceParser] | None:
        """Remove a registration. Returns the removed class, or None.

        Also drops any MIME-type index entries that pointed to this class.
        """
        cls = self._by_name.pop(name, None)
        if cls is not None:
            for mime_type in list(self._by_mime_type):
                if self._by_mime_type[mime_type] is cls:
                    del self._by_mime_type[mime_type]
        return cls

    def clear(self) -> None:
        """Drop all registrations. Primarily for tests."""
        self._by_name.clear()
        self._by_mime_type.clear()

    # --- Lookup -------------------------------------------------------

    def get(self, name: str) -> type[SourceParser] | None:
        """Resolve a parser class by name. ``None`` if unknown."""
        return self._by_name.get(name)

    def get_by_mime_type(self, mime_type: str) -> type[SourceParser] | None:
        """Resolve a parser class by MIME type. ``None`` if unknown."""
        return self._by_mime_type.get(mime_type)

    def has(self, name: str) -> bool:
        """Whether a parser with this name is registered."""
        return name in self._by_name

    def list_names(self) -> list[str]:
        """All registered parser names, sorted."""
        return sorted(self._by_name)

    def list_mime_types(self) -> list[str]:
        """All MIME types with a registered parser, sorted."""
        return sorted(self._by_mime_type)

    def list_classes(self) -> list[type[SourceParser]]:
        """All registered parser classes, in registration order."""
        return list(self._by_name.values())

    def __len__(self) -> int:
        return len(self._by_name)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._by_name

    def __iter__(self):
        return iter(self._by_name)

    def __repr__(self) -> str:
        return (
            f"ParserRegistry({len(self._by_name)} parsers: {sorted(self._by_name)}, "
            f"{len(self._by_mime_type)} MIME types)"
        )


# Module-level default. Populated by :mod:`kaos_source.parsers` on
# import (Track 1 chunk 6).
default_parser_registry = ParserRegistry()


__all__ = ["ParserRegistry", "default_parser_registry"]
