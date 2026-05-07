"""Federal Register API connector — :class:`ApiConnector` subclass.

For chunk 5 the connector class only carries metadata. It exists so the
:class:`ApiRegistry` has something to hold and so callers can introspect
which capabilities the API advertises ("does it support search? get?
preview?"). Capability methods (``search``, ``get``, ...) wrap the raw
:mod:`kaos_source.apis.federal_register.client` functions in a follow-up
chunk.
"""

from __future__ import annotations

from kaos_source.base.api_connector import ApiConnector
from kaos_source.base.capabilities import SourceCapability
from kaos_source.base.metadata import ApiMetadata


class FederalRegisterApiConnector(ApiConnector):
    """Federal Register public API (no authentication required)."""

    @classmethod
    def metadata(cls) -> ApiMetadata:
        return ApiMetadata(
            name="federal_register",
            description="Federal Register public REST API — no authentication required.",
            base_url="https://www.federalregister.gov/api/v1",
            requires_auth=False,
            capabilities=(
                SourceCapability.SEARCH,
                SourceCapability.GET,
                SourceCapability.DISCOVER,
            ),
        )


__all__ = ["FederalRegisterApiConnector"]
