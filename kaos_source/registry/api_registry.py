"""ApiRegistry — name → :class:`ApiConnector` class.

Mirrors :class:`kaos_agents.registry.pattern_registry.PatternRegistry`
shape but for httpx-backed REST API connectors. Holds *classes*
(not instances) because:

- Each API call typically constructs a fresh ``httpx.AsyncClient`` so
  there's no per-instance state worth memoizing at the registry level.
- Settings instantiation differs per call (search vs. get vs. preview
  may want different timeouts), so deferring construction to call-time
  with explicit settings is cleaner than holding pre-configured
  instances.
- Tools that consume an api connector typically want the *class* so
  they can route by name then instantiate with the request's settings.

Populated by :mod:`kaos_source.apis` on import (Track 1 chunk 5).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kaos_core.exceptions import RegistryError

if TYPE_CHECKING:
    from kaos_source.base.api_connector import ApiConnector


class ApiRegistry:
    """Catalogue of name → :class:`ApiConnector` subclass.

    Lookup is by api name (matching :attr:`ApiMetadata.name`:
    ``"federal_register"``, ``"ecfr"``, ``"edgar"``, ``"govinfo"``,
    ``"gleif"``).

    Typical use::

        from kaos_source.registry import default_api_registry

        cls = default_api_registry.get("federal_register")
        connector = cls()
        results = await connector.search(query="rule", settings=settings)
    """

    __slots__ = ("_by_name",)

    def __init__(self) -> None:
        self._by_name: dict[str, type[ApiConnector]] = {}

    # --- Mutation -----------------------------------------------------

    def register(
        self,
        name: str,
        cls: type[ApiConnector],
        *,
        force: bool = False,
    ) -> None:
        """Register an api connector class under ``name``.

        Args:
            name: API discriminator (typically ``cls.metadata().name``).
            cls: A :class:`ApiConnector` subclass.
            force: When ``True``, replaces any existing registration
                for this name. Default ``False`` raises on conflict.

        Raises:
            RegistryError: If a different class is already registered
                under ``name`` and ``force`` is False.
        """
        existing = self._by_name.get(name)
        if existing is not None and existing is not cls and not force:
            raise RegistryError(
                "Api connector already registered with this name",
                api_name=name,
                existing=existing.__name__,
                attempted=cls.__name__,
            )
        self._by_name[name] = cls

    def unregister(self, name: str) -> type[ApiConnector] | None:
        """Remove a registration. Returns the removed class, or None."""
        return self._by_name.pop(name, None)

    def clear(self) -> None:
        """Drop all registrations. Primarily for tests."""
        self._by_name.clear()

    # --- Lookup -------------------------------------------------------

    def get(self, name: str) -> type[ApiConnector] | None:
        """Resolve an api connector class by name. ``None`` if unknown."""
        return self._by_name.get(name)

    def has(self, name: str) -> bool:
        """Whether an api with this name is registered."""
        return name in self._by_name

    def list_names(self) -> list[str]:
        """All registered api names, sorted."""
        return sorted(self._by_name)

    def list_classes(self) -> list[type[ApiConnector]]:
        """All registered api classes, in registration order."""
        return list(self._by_name.values())

    def __len__(self) -> int:
        return len(self._by_name)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._by_name

    def __iter__(self):
        return iter(self._by_name)

    def __repr__(self) -> str:
        return f"ApiRegistry({len(self._by_name)} apis: {sorted(self._by_name)})"


# Module-level default. Populated by :mod:`kaos_source.apis` on
# import (Track 1 chunk 5).
default_api_registry = ApiRegistry()


__all__ = ["ApiRegistry", "default_api_registry"]
