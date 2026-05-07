"""ConnectorRegistry — :class:`SourceKind` → :class:`SourceConnector` class.

Mirrors :class:`kaos_agents.registry.pattern_registry.PatternRegistry`
shape: holds *classes* keyed by :class:`SourceKind` (the enum value
that the subclass declares as its class-level ``kind`` attribute).

Why classes (not instances): some connectors are stateful in ways that
require fresh instances per :class:`SourceService` — e.g.
:class:`MemoryConnector` accumulates ``put_bytes()`` registrations
that must NOT leak between services / test runs. The pre-chunk-4
``SourceService.__init__`` instantiated each connector freshly per
service. Holding classes here preserves that fresh-per-service
contract while still giving us a discoverable catalogue.

Auto-registration is explicit (called from
:mod:`kaos_source.connectors.__init__`) for the same reasons given in
:mod:`kaos_source.registry`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kaos_core.exceptions import RegistryError

from kaos_source.models import SourceKind

if TYPE_CHECKING:
    from kaos_source.connectors.base import SourceConnector


class ConnectorRegistry:
    """Catalogue of :class:`SourceKind` → :class:`SourceConnector` subclass.

    Each registered class advertises its kind via the class-level
    ``kind`` attribute (e.g. ``FilesystemConnector.kind ==
    SourceKind.FILESYSTEM``).

    Typical use::

        from kaos_source.registry import default_connector_registry
        from kaos_source.models import SourceKind

        cls = default_connector_registry.get(SourceKind.FILESYSTEM)
        if cls is not None:
            connector = cls()
    """

    __slots__ = ("_by_kind",)

    def __init__(self) -> None:
        self._by_kind: dict[SourceKind, type[SourceConnector]] = {}

    # --- Mutation -----------------------------------------------------

    def register(
        self,
        cls: type[SourceConnector],
        *,
        force: bool = False,
    ) -> None:
        """Register a connector class under its ``cls.kind``.

        Args:
            cls: A :class:`SourceConnector` subclass with its
                ``kind`` class attribute set.
            force: When ``True``, replaces any existing registration
                for this kind. Default ``False`` raises on conflict.

        Raises:
            RegistryError: If a different class is already registered
                under the same kind and ``force`` is False.
        """
        kind = cls.kind
        existing = self._by_kind.get(kind)
        if existing is not None and existing is not cls and not force:
            raise RegistryError(
                "Connector class already registered with this kind",
                source_kind=kind.value,
                existing=existing.__name__,
                attempted=cls.__name__,
            )
        self._by_kind[kind] = cls

    def unregister(self, kind: SourceKind) -> type[SourceConnector] | None:
        """Remove a registration. Returns the removed class, or None."""
        return self._by_kind.pop(kind, None)

    def clear(self) -> None:
        """Drop all registrations. Primarily for tests."""
        self._by_kind.clear()

    # --- Lookup -------------------------------------------------------

    def get(self, kind: SourceKind) -> type[SourceConnector] | None:
        """Resolve a connector class by source kind. ``None`` if unknown."""
        return self._by_kind.get(kind)

    def has(self, kind: SourceKind) -> bool:
        """Whether a connector for this kind is registered."""
        return kind in self._by_kind

    def list_kinds(self) -> list[SourceKind]:
        """All registered source kinds, in registration order."""
        return list(self._by_kind)

    def list_classes(self) -> list[type[SourceConnector]]:
        """All registered connector classes, in registration order."""
        return list(self._by_kind.values())

    def instantiate_all(self) -> list[SourceConnector]:
        """Construct one fresh instance of every registered connector class.

        Used by :class:`SourceService.__init__` when no explicit
        ``connectors=[…]`` list is provided. Each call returns brand-new
        instances — no shared state between services.
        """
        return [cls() for cls in self._by_kind.values()]

    def __len__(self) -> int:
        return len(self._by_kind)

    def __contains__(self, kind: object) -> bool:
        return isinstance(kind, SourceKind) and kind in self._by_kind

    def __iter__(self):
        return iter(self._by_kind)

    def __repr__(self) -> str:
        kinds = sorted(k.value for k in self._by_kind)
        return f"ConnectorRegistry({len(self._by_kind)} connectors: {kinds})"


# Module-level default. Populated by :mod:`kaos_source.connectors` on
# import — see that module's ``__init__.py`` for the explicit
# registration calls.
default_connector_registry = ConnectorRegistry()


__all__ = ["ConnectorRegistry", "default_connector_registry"]
