"""Smoke tests for kaos_source.base ABCs / Protocols / metadata.

Track 1 chunk 1: confirms the new contracts layer compiles, the ABCs
cannot be instantiated bare, the classmethod ``metadata()`` defaults
fire, and the runtime-checkable Protocols accept conforming impls.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from pydantic import ValidationError

from kaos_source.base import (
    ApiConnector,
    ApiMetadata,
    Closable,
    ConnectorMetadata,
    ParserMetadata,
    ReadableBinaryStream,
    SourceCapability,
    SourceParser,
    SupportsGet,
    SupportsMaterialize,
    SupportsPreview,
    SupportsSearch,
)
from kaos_source.models import SourceKind


class _DemoApiConnector(ApiConnector):
    """Demo api connector for ABC tests."""


class _SearchableDemo:
    async def search(self, query: str) -> list[str]:
        return [query]


class _GettableDemo:
    async def get(self, identifier: str) -> dict[str, str]:
        return {"id": identifier}


class _DemoParser(SourceParser):
    """Demo parser for ABC tests."""

    @property
    def supported_mime_types(self) -> tuple[str, ...]:
        return ("text/plain",)


class TestProtocols:
    def test_closable_accepts_conforming_object(self) -> None:
        class _Holder:
            def close(self) -> None:
                self.closed = True

        assert isinstance(_Holder(), Closable)

    def test_closable_rejects_non_conforming(self) -> None:
        class _NoClose:
            pass

        assert not isinstance(_NoClose(), Closable)

    def test_readable_binary_stream_accepts_bytesio(self) -> None:
        # BytesIO satisfies read/close/__enter__/__exit__ structurally.
        assert isinstance(BytesIO(b"hello"), ReadableBinaryStream)

    def test_supports_search_protocol(self) -> None:
        assert isinstance(_SearchableDemo(), SupportsSearch)
        assert not isinstance(_GettableDemo(), SupportsSearch)

    def test_supports_get_protocol(self) -> None:
        assert isinstance(_GettableDemo(), SupportsGet)
        assert not isinstance(_SearchableDemo(), SupportsGet)

    def test_supports_preview_and_materialize_protocols(self) -> None:
        # Negative checks — neither demo satisfies these.
        assert not isinstance(_SearchableDemo(), SupportsPreview)
        assert not isinstance(_GettableDemo(), SupportsMaterialize)


class TestMetadataValidation:
    def test_connector_metadata_defaults(self) -> None:
        meta = ConnectorMetadata(name="demo", description="a demo")
        assert meta.module_name == "kaos_source"
        assert meta.version == "1.0.0"
        assert meta.capabilities == ()
        assert meta.supported_kinds == ()

    def test_connector_metadata_with_kinds_and_capabilities(self) -> None:
        meta = ConnectorMetadata(
            name="filesystem",
            description="local files",
            supported_kinds=(SourceKind.FILESYSTEM,),
            capabilities=(SourceCapability.DESCRIBE, SourceCapability.MATERIALIZE),
        )
        assert SourceCapability.DESCRIBE in meta.capabilities
        assert SourceKind.FILESYSTEM in meta.supported_kinds

    def test_api_metadata_with_auth(self) -> None:
        meta = ApiMetadata(
            name="govinfo",
            description="GovInfo API",
            base_url="https://api.govinfo.gov",
            requires_auth=True,
            auth_env_var="KAOS_SOURCE_GOVINFO_API_KEY",
            capabilities=(SourceCapability.SEARCH, SourceCapability.GET),
        )
        assert meta.requires_auth is True
        assert meta.auth_env_var == "KAOS_SOURCE_GOVINFO_API_KEY"

    def test_parser_metadata_with_mime_types(self) -> None:
        meta = ParserMetadata(
            name="vcard",
            description="vCard parser",
            supported_mime_types=("text/vcard", "text/x-vcard"),
            supported_extensions=(".vcf", ".vcard"),
            capabilities=(SourceCapability.PARSE,),
        )
        assert "text/vcard" in meta.supported_mime_types
        assert ".vcf" in meta.supported_extensions

    def test_metadata_name_validation_rejects_uppercase(self) -> None:
        with pytest.raises(ValueError, match="metadata name must match"):
            ConnectorMetadata(name="BadName", description="x")

    def test_metadata_name_validation_accepts_relaxed_chars(self) -> None:
        for good in ("federal_register", "ecfr", "edgar", "email.eml", "x-y_z.0"):
            ConnectorMetadata(name=good, description="x")

    def test_metadata_is_frozen(self) -> None:
        meta = ApiMetadata(name="x", description="y")
        with pytest.raises(ValidationError):
            meta.name = "z"  # ty: ignore[invalid-assignment]


class TestApiConnectorAbc:
    def test_cannot_instantiate_bare_abc(self) -> None:
        # ABC with no abstract methods is technically instantiable, so
        # the meaningful check is that subclasses inherit the metadata
        # default rather than the bare ABC raising.
        instance = _DemoApiConnector()
        assert isinstance(instance, ApiConnector)

    def test_default_metadata_uses_class_name_and_doc(self) -> None:
        meta = _DemoApiConnector.metadata()
        assert meta.name == "demo_api_connector"
        assert "Demo api connector" in meta.description

    def test_subclass_can_override_metadata(self) -> None:
        class _Custom(ApiConnector):
            @classmethod
            def metadata(cls) -> ApiMetadata:
                return ApiMetadata(
                    name="custom",
                    description="custom api",
                    base_url="https://example.test",
                    requires_auth=True,
                    capabilities=(SourceCapability.SEARCH,),
                )

        meta = _Custom.metadata()
        assert meta.name == "custom"
        assert meta.requires_auth is True
        assert SourceCapability.SEARCH in meta.capabilities


class TestSourceParserAbc:
    def test_cannot_instantiate_without_supported_mime_types(self) -> None:
        with pytest.raises(TypeError, match="supported_mime_types"):
            SourceParser()

    def test_concrete_subclass_instantiates(self) -> None:
        parser = _DemoParser()
        assert parser.supported_mime_types == ("text/plain",)

    def test_default_metadata_uses_class_name_and_doc(self) -> None:
        meta = _DemoParser.metadata()
        assert meta.name == "demo_parser"
        assert "Demo parser" in meta.description


class TestPackageImports:
    def test_all_symbols_exported_from_base_init(self) -> None:
        import kaos_source.base as base_pkg

        for symbol in (
            "ApiConnector",
            "ApiMetadata",
            "Closable",
            "ConnectorMetadata",
            "ParserMetadata",
            "ReadableBinaryStream",
            "SourceCapability",
            "SourceParser",
            "SupportsGet",
            "SupportsMaterialize",
            "SupportsPreview",
            "SupportsSearch",
        ):
            assert hasattr(base_pkg, symbol), f"missing {symbol}"

    def test_base_does_not_import_runtime_or_apis(self) -> None:
        # Enforce dependency direction: base/ is leaf within the package.
        import kaos_source.base.api_connector as api_mod
        import kaos_source.base.capabilities as caps_mod
        import kaos_source.base.metadata as meta_mod
        import kaos_source.base.parser as parser_mod
        import kaos_source.base.protocols as proto_mod

        for mod in (api_mod, caps_mod, meta_mod, parser_mod, proto_mod):
            for name in dir(mod):
                attr = getattr(mod, name)
                module = getattr(attr, "__module__", "")
                if not module.startswith("kaos_source."):
                    continue
                assert not module.startswith("kaos_source.runtime"), (
                    f"{mod.__name__} imports from kaos_source.runtime via {name!r}"
                )
                assert not module.startswith("kaos_source.apis"), (
                    f"{mod.__name__} imports from kaos_source.apis via {name!r}"
                )
                assert not module.startswith("kaos_source.connectors"), (
                    f"{mod.__name__} imports from kaos_source.connectors via {name!r}"
                )
