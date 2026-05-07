"""ECFRApiConnector — :class:`ApiConnector` subclass for the eCFR API.

For Track 1 chunk 5 the connector class only carries
:meth:`metadata`. The capability methods (search/get/preview/
materialize) are still served by the free functions in
:mod:`kaos_source.apis.ecfr.client`; later chunks will wrap them as
instance methods. The class exists so :class:`ApiRegistry` has
something to hold and so callers can introspect "what does this API
support" without instantiating an httpx client.
"""

from __future__ import annotations

from kaos_source.base.api_connector import ApiConnector
from kaos_source.base.capabilities import SourceCapability
from kaos_source.base.metadata import ApiMetadata


class ECFRApiConnector(ApiConnector):
    """Electronic Code of Federal Regulations public API (no authentication required)."""

    @classmethod
    def metadata(cls) -> ApiMetadata:
        return ApiMetadata(
            name="ecfr",
            description=(
                "Electronic Code of Federal Regulations public REST API — "
                "no authentication required."
            ),
            base_url="https://www.ecfr.gov/api",
            requires_auth=False,
            capabilities=(
                SourceCapability.GET,
                SourceCapability.SEARCH,
                SourceCapability.DISCOVER,
            ),
        )


__all__ = ["ECFRApiConnector"]
