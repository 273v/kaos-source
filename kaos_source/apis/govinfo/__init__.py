"""GovInfo (US Government Publishing Office) API subpackage.

Public surface (preferred imports for new code)::

    from kaos_source.apis.govinfo import (
        GovInfoApiConnector,
        KaosSourceGovInfoSettings,
        register_govinfo_tools,
    )
    from kaos_source.apis.govinfo.client import search, get_package, get_collections
    from kaos_source.apis.govinfo.models import (
        GovInfoCollection, GovInfoPackage, GovInfoSearchResponse, GovInfoSearchResult,
    )

Importing this subpackage triggers auto-registration of
:class:`GovInfoApiConnector` into
:data:`kaos_source.registry.default_api_registry` under the name
``"govinfo"``.
"""

from __future__ import annotations

from kaos_source.apis.govinfo.client import (
    get_collections,
    get_package,
    search,
)
from kaos_source.apis.govinfo.connector import GovInfoApiConnector
from kaos_source.apis.govinfo.models import (
    GovInfoCollection,
    GovInfoPackage,
    GovInfoSearchResponse,
    GovInfoSearchResult,
)
from kaos_source.apis.govinfo.tools import (
    GovInfoCollectionsTool,
    GovInfoGetPackageTool,
    GovInfoSearchTool,
    register_govinfo_tools,
)
from kaos_source.registry import default_api_registry
from kaos_source.settings.govinfo import KaosSourceGovInfoSettings

default_api_registry.register("govinfo", GovInfoApiConnector, force=True)


__all__ = [
    "GovInfoApiConnector",
    "GovInfoCollection",
    "GovInfoCollectionsTool",
    "GovInfoGetPackageTool",
    "GovInfoPackage",
    "GovInfoSearchResponse",
    "GovInfoSearchResult",
    "GovInfoSearchTool",
    "KaosSourceGovInfoSettings",
    "get_collections",
    "get_package",
    "register_govinfo_tools",
    "search",
]
