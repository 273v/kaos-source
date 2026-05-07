"""GLEIF API connector — :class:`ApiConnector` subclass.

For chunk 5 the connector class only carries metadata. It exists so the
:class:`ApiRegistry` has something to hold and so callers can introspect
which capabilities the API advertises ("does it support search? get?
resolve?"). Capability methods (``search``, ``get``, ``resolve``) wrap
the raw :mod:`kaos_source.apis.gleif.client` functions in a follow-up
chunk.

GLEIF stands apart from the other ``apis/`` connectors in that it has
*no* dedicated settings class — the public API is unauthenticated and
the only knob is a per-call ``timeout``.
"""

from __future__ import annotations

from kaos_source.base.api_connector import ApiConnector
from kaos_source.base.capabilities import SourceCapability
from kaos_source.base.metadata import ApiMetadata


class GleifApiConnector(ApiConnector):
    """GLEIF Global Legal Entity Identifier public API (no authentication required).

    Covers ~2.5M entities globally — financial institutions, public
    companies, funds, etc.
    """

    @classmethod
    def metadata(cls) -> ApiMetadata:
        return ApiMetadata(
            name="gleif",
            description=(
                "GLEIF (Global Legal Entity Identifier) public REST API — "
                "no authentication required."
            ),
            base_url="https://api.gleif.org/api/v1",
            requires_auth=False,
            capabilities=(
                SourceCapability.SEARCH,
                SourceCapability.GET,
                SourceCapability.RESOLVE,
            ),
        )


__all__ = ["GleifApiConnector"]
