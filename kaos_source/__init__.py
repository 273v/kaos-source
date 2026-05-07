"""kaos-source — KAOS-native source discovery, retrieval, and parsing.

After Track 1 the package is organized as:

- :mod:`kaos_source.base`        — ABCs and Protocols (the contracts)
- :mod:`kaos_source.runtime`     — execution machinery (SourceService,
                                   policy, materialization, ...)
- :mod:`kaos_source.registry`    — three catalogues:
                                   :class:`ConnectorRegistry`,
                                   :class:`ApiRegistry`,
                                   :class:`ParserRegistry`
- :mod:`kaos_source.settings`    — one :class:`ModuleSettings` per file
- :mod:`kaos_source.connectors`  — transport SourceConnector
                                   implementations (filesystem, archive,
                                   http, browser, memory)
- :mod:`kaos_source.apis`        — REST ApiConnector subpackages
                                   (federal_register, ecfr, edgar,
                                   govinfo, gleif)
- :mod:`kaos_source.parsers`     — SourceParser implementations
                                   (vcard, email/{eml,mbox,family},
                                   pacer, file_meta, image_meta)

Importing this package triggers chain-imports of ``connectors``, ``apis``,
and ``parsers``, which in turn populate the three default registries
via their respective ``__init__.py`` files. Code that only needs the
registry catalogue (e.g. UI introspection of "what does kaos-source
expose?") can ``import kaos_source`` and read from the registries
without reaching for the tool layer.
"""

# Trigger auto-registration of the apis/ and parsers/ subpackages so
# default_api_registry and default_parser_registry are populated when
# anyone does ``import kaos_source``. ``connectors`` is already imported
# transitively by the SourceConnector re-export below.
from kaos_source import apis as _apis  # noqa: F401
from kaos_source import parsers as _parsers  # noqa: F401
from kaos_source._version import __version__
from kaos_source.apis.ecfr.tools import register_ecfr_tools
from kaos_source.apis.edgar.tools import register_edgar_tools
from kaos_source.apis.federal_register.tools import register_federal_register_tools
from kaos_source.apis.gleif.tools import register_gleif_tools
from kaos_source.apis.govinfo.tools import register_govinfo_tools

# --- ABCs + Protocols (Track 1 chunk 1) -------------------------------------
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
from kaos_source.connectors import (
    ArchiveConnector,
    BrowserConnector,
    FilesystemConnector,
    HttpConnector,
    MemoryConnector,
    SourceConnector,
)
from kaos_source.errors import (
    SourceAccessError,
    SourceError,
    SourceErrorInfo,
    SourceMaterializationError,
    SourceNotFoundError,
    SourcePolicyError,
    SourceTransientError,
    SourceValidationError,
)
from kaos_source.models import (
    SourceDescriptor,
    SourceJob,
    SourceJobResult,
    SourceJobStatus,
    SourceKind,
    SourceLocator,
    SourceMaterialization,
    SourceOperation,
    SourcePage,
    SourcePreview,
    SourceProvenance,
)
from kaos_source.options import (
    SourceDiscoverOptions,
    SourceMaterializeOptions,
    SourcePreviewOptions,
)
from kaos_source.parsers import register_forensics_tools
from kaos_source.parsers.pacer.tools import register_pacer_tools
from kaos_source.parsers.vcard.tools import register_vcard_tools

# --- Registries (Track 1 chunk 4) -------------------------------------------
from kaos_source.registry import (
    ApiRegistry,
    ConnectorRegistry,
    ParserRegistry,
    default_api_registry,
    default_connector_registry,
    default_parser_registry,
)
from kaos_source.runtime.service import SourceService
from kaos_source.runtime.tools import register_source_tools

__all__ = [
    "ApiConnector",
    "ApiMetadata",
    "ApiRegistry",
    "ArchiveConnector",
    "BrowserConnector",
    "Closable",
    "ConnectorMetadata",
    "ConnectorRegistry",
    "FilesystemConnector",
    "HttpConnector",
    "MemoryConnector",
    "ParserMetadata",
    "ParserRegistry",
    "ReadableBinaryStream",
    "SourceAccessError",
    "SourceCapability",
    "SourceConnector",
    "SourceDescriptor",
    "SourceDiscoverOptions",
    "SourceError",
    "SourceErrorInfo",
    "SourceJob",
    "SourceJobResult",
    "SourceJobStatus",
    "SourceKind",
    "SourceLocator",
    "SourceMaterialization",
    "SourceMaterializationError",
    "SourceMaterializeOptions",
    "SourceNotFoundError",
    "SourceOperation",
    "SourcePage",
    "SourceParser",
    "SourcePolicyError",
    "SourcePreview",
    "SourcePreviewOptions",
    "SourceProvenance",
    "SourceService",
    "SourceTransientError",
    "SourceValidationError",
    "SupportsGet",
    "SupportsMaterialize",
    "SupportsPreview",
    "SupportsSearch",
    "__version__",
    "default_api_registry",
    "default_connector_registry",
    "default_parser_registry",
    "register_ecfr_tools",
    "register_edgar_tools",
    "register_federal_register_tools",
    "register_forensics_tools",
    "register_gleif_tools",
    "register_govinfo_tools",
    "register_pacer_tools",
    "register_source_tools",
    "register_vcard_tools",
]
