"""Tests for kaos_source.registry — Track 1 chunk 4.

Covers all three registries:
- :class:`ConnectorRegistry` (SourceKind → SourceConnector instance)
- :class:`ApiRegistry` (name → ApiConnector class)
- :class:`ParserRegistry` (name → SourceParser class + MIME index)

Plus the auto-population invariant: importing ``kaos_source.connectors``
populates ``default_connector_registry`` with the 5 transport
connectors.
"""

from __future__ import annotations

import pytest
from kaos_core.exceptions import RegistryError

from kaos_source.base import (
    ApiConnector,
    ApiMetadata,
    ParserMetadata,
    SourceCapability,
    SourceParser,
)
from kaos_source.connectors import (
    ArchiveConnector,
    BrowserConnector,
    FilesystemConnector,
    HttpConnector,
    MemoryConnector,
)
from kaos_source.models import SourceKind
from kaos_source.registry import (
    ApiRegistry,
    ConnectorRegistry,
    ParserRegistry,
    default_api_registry,
    default_connector_registry,
    default_parser_registry,
)


class _DemoApi(ApiConnector):
    @classmethod
    def metadata(cls) -> ApiMetadata:
        return ApiMetadata(name="demo_api", description="demo")


class _OtherDemoApi(ApiConnector):
    @classmethod
    def metadata(cls) -> ApiMetadata:
        return ApiMetadata(name="demo_api", description="other demo")


class _VcardLikeParser(SourceParser):
    @classmethod
    def metadata(cls) -> ParserMetadata:
        return ParserMetadata(
            name="vcard_like",
            description="vcard-like parser",
            supported_mime_types=("text/vcard", "text/x-vcard"),
            capabilities=(SourceCapability.PARSE,),
        )

    @property
    def supported_mime_types(self) -> tuple[str, ...]:
        return ("text/vcard", "text/x-vcard")


class _ConflictingMimeParser(SourceParser):
    @classmethod
    def metadata(cls) -> ParserMetadata:
        return ParserMetadata(
            name="conflicting",
            description="parser claiming text/vcard",
            supported_mime_types=("text/vcard",),
        )

    @property
    def supported_mime_types(self) -> tuple[str, ...]:
        return ("text/vcard",)


class _OtherMemoryConnector(MemoryConnector):
    """Subclass for collision testing — shares ``kind = SourceKind.MEMORY``."""


class TestConnectorRegistry:
    def test_register_and_get(self) -> None:
        reg = ConnectorRegistry()
        reg.register(MemoryConnector)
        assert reg.get(SourceKind.MEMORY) is MemoryConnector
        assert reg.has(SourceKind.MEMORY)
        assert SourceKind.MEMORY in reg

    def test_register_duplicate_kind_raises(self) -> None:
        reg = ConnectorRegistry()
        reg.register(MemoryConnector)
        with pytest.raises(RegistryError):
            reg.register(_OtherMemoryConnector)  # different class, same kind

    def test_same_class_re_register_idempotent(self) -> None:
        reg = ConnectorRegistry()
        reg.register(MemoryConnector)
        reg.register(MemoryConnector)  # same class — no-op, no raise
        assert reg.get(SourceKind.MEMORY) is MemoryConnector

    def test_force_overwrites(self) -> None:
        reg = ConnectorRegistry()
        reg.register(MemoryConnector)
        reg.register(_OtherMemoryConnector, force=True)
        assert reg.get(SourceKind.MEMORY) is _OtherMemoryConnector

    def test_unregister_returns_removed(self) -> None:
        reg = ConnectorRegistry()
        reg.register(MemoryConnector)
        assert reg.unregister(SourceKind.MEMORY) is MemoryConnector
        assert reg.get(SourceKind.MEMORY) is None

    def test_clear(self) -> None:
        reg = ConnectorRegistry()
        reg.register(MemoryConnector)
        reg.clear()
        assert len(reg) == 0

    def test_default_registry_has_5_transports(self) -> None:
        # Importing kaos_source.connectors should auto-populate.
        assert SourceKind.FILESYSTEM in default_connector_registry
        assert SourceKind.ARCHIVE in default_connector_registry
        assert SourceKind.MEMORY in default_connector_registry
        assert SourceKind.HTTP in default_connector_registry
        assert SourceKind.BROWSER in default_connector_registry

    def test_default_registry_classes_match(self) -> None:
        get = default_connector_registry.get
        assert get(SourceKind.FILESYSTEM) is FilesystemConnector
        assert get(SourceKind.ARCHIVE) is ArchiveConnector
        assert get(SourceKind.MEMORY) is MemoryConnector
        assert get(SourceKind.HTTP) is HttpConnector
        assert get(SourceKind.BROWSER) is BrowserConnector

    def test_instantiate_all_returns_fresh_instances(self) -> None:
        # Critical invariant: each call returns brand-new instances so
        # stateful connectors (MemoryConnector) don't leak across
        # SourceService instances or test runs.
        a = default_connector_registry.instantiate_all()
        b = default_connector_registry.instantiate_all()
        assert len(a) == 5
        assert len(b) == 5
        for ai, bi in zip(a, b, strict=True):
            assert type(ai) is type(bi)
            assert ai is not bi

    def test_repr_includes_kind_names(self) -> None:
        reg = ConnectorRegistry()
        reg.register(MemoryConnector)
        assert "memory" in repr(reg)


class TestApiRegistry:
    def test_register_and_get(self) -> None:
        reg = ApiRegistry()
        reg.register("demo", _DemoApi)
        assert reg.get("demo") is _DemoApi
        assert "demo" in reg
        assert reg.has("demo")

    def test_duplicate_name_raises(self) -> None:
        reg = ApiRegistry()
        reg.register("demo", _DemoApi)
        with pytest.raises(RegistryError):
            reg.register("demo", _OtherDemoApi)

    def test_same_class_re_register_idempotent(self) -> None:
        reg = ApiRegistry()
        reg.register("demo", _DemoApi)
        # Re-registering the same class is a no-op (matches PatternRegistry).
        reg.register("demo", _DemoApi)
        assert reg.get("demo") is _DemoApi

    def test_force_overwrites(self) -> None:
        reg = ApiRegistry()
        reg.register("demo", _DemoApi)
        reg.register("demo", _OtherDemoApi, force=True)
        assert reg.get("demo") is _OtherDemoApi

    def test_get_unknown_returns_none(self) -> None:
        reg = ApiRegistry()
        assert reg.get("missing") is None

    def test_list_names_sorted(self) -> None:
        reg = ApiRegistry()
        reg.register("zebra", _DemoApi)
        reg.register("alpha", _OtherDemoApi)
        assert reg.list_names() == ["alpha", "zebra"]

    def test_default_api_registry_populated_after_chunk_5(self) -> None:
        # Chunk 5 wired auto-registration in kaos_source/apis/__init__.py.
        # Importing kaos_source (which we did at module load via test imports)
        # transitively imports kaos_source.apis through the connector shims,
        # populating all 5 builtin api connectors.
        import kaos_source.apis  # noqa: F401  ensure chain-import has fired

        for name in ("federal_register", "ecfr", "edgar", "govinfo", "gleif"):
            assert name in default_api_registry, f"{name} should be registered"
        # Each registered class is an ApiConnector subclass and exposes metadata.
        from kaos_source.base.api_connector import ApiConnector

        for name in default_api_registry.list_names():
            cls = default_api_registry.get(name)
            assert cls is not None
            assert issubclass(cls, ApiConnector)
            meta = cls.metadata()
            assert meta.name == name


class TestParserRegistry:
    def test_register_and_get(self) -> None:
        reg = ParserRegistry()
        reg.register("vcard_like", _VcardLikeParser)
        assert reg.get("vcard_like") is _VcardLikeParser

    def test_mime_secondary_index(self) -> None:
        reg = ParserRegistry()
        reg.register("vcard_like", _VcardLikeParser)
        assert reg.get_by_mime_type("text/vcard") is _VcardLikeParser
        assert reg.get_by_mime_type("text/x-vcard") is _VcardLikeParser
        assert reg.get_by_mime_type("application/pdf") is None

    def test_duplicate_name_raises(self) -> None:
        reg = ParserRegistry()
        reg.register("p", _VcardLikeParser)
        with pytest.raises(RegistryError):
            reg.register("p", _ConflictingMimeParser)

    def test_mime_collision_raises(self) -> None:
        reg = ParserRegistry()
        reg.register("vcard_like", _VcardLikeParser)
        with pytest.raises(RegistryError, match="MIME type"):
            reg.register("conflicting", _ConflictingMimeParser)

    def test_force_resolves_mime_collision(self) -> None:
        reg = ParserRegistry()
        reg.register("vcard_like", _VcardLikeParser)
        reg.register("conflicting", _ConflictingMimeParser, force=True)
        assert reg.get_by_mime_type("text/vcard") is _ConflictingMimeParser

    def test_unregister_drops_mime_index(self) -> None:
        reg = ParserRegistry()
        reg.register("vcard_like", _VcardLikeParser)
        assert reg.get_by_mime_type("text/vcard") is _VcardLikeParser
        reg.unregister("vcard_like")
        assert reg.get_by_mime_type("text/vcard") is None

    def test_list_mime_types_sorted(self) -> None:
        reg = ParserRegistry()
        reg.register("vcard_like", _VcardLikeParser)
        assert reg.list_mime_types() == ["text/vcard", "text/x-vcard"]

    def test_default_parser_registry_starts_empty(self) -> None:
        # Parsers register themselves in chunk 6; chunk 4 leaves it empty.
        assert len(default_parser_registry) == 0


class TestServiceConsumesRegistry:
    def test_default_service_picks_up_registered_connectors(self) -> None:
        # SourceService() with no connectors=arg now reads the registry.
        from kaos_source.runtime.service import SourceService

        service = SourceService()
        # All 5 transport connectors should be wired in.
        for kind in (
            SourceKind.FILESYSTEM,
            SourceKind.ARCHIVE,
            SourceKind.MEMORY,
            SourceKind.HTTP,
            SourceKind.BROWSER,
        ):
            assert kind in service._connectors

    def test_explicit_connectors_override_registry(self) -> None:
        from kaos_source.runtime.service import SourceService

        only_memory = MemoryConnector()
        service = SourceService(connectors=[only_memory])
        assert SourceKind.MEMORY in service._connectors
        assert SourceKind.HTTP not in service._connectors
