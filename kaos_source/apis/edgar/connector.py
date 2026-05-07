"""SEC EDGAR API connector — :class:`ApiConnector` subclass.

For chunk 5 the connector class only carries metadata. It exists so the
:class:`ApiRegistry` has something to hold and so callers can introspect
which capabilities the API advertises ("does it support search? get?
resolve?"). Capability methods (``search``, ``get``, ``resolve``) wrap the
raw :mod:`kaos_source.apis.edgar.client` functions in a follow-up chunk.
"""

from __future__ import annotations

from kaos_source.base.api_connector import ApiConnector
from kaos_source.base.capabilities import SourceCapability
from kaos_source.base.metadata import ApiMetadata


class EdgarApiConnector(ApiConnector):
    """SEC EDGAR public API.

    No API key required, but a ``User-Agent`` header identifying your
    organization is mandatory (format: ``"YourCompany contact@company.com"``).
    The SEC enforces this and will block requests that omit a descriptive
    User-Agent. Rate limit: 10 requests/second.
    """

    @classmethod
    def metadata(cls) -> ApiMetadata:
        return ApiMetadata(
            name="edgar",
            description="SEC EDGAR public REST API — User-Agent required, no API key.",
            base_url="https://efts.sec.gov/LATEST",
            requires_auth=False,  # No key, but UA is checked
            auth_env_var="KAOS_SOURCE_EDGAR_USER_AGENT",
            capabilities=(
                SourceCapability.SEARCH,
                SourceCapability.GET,
                SourceCapability.RESOLVE,
            ),
        )


__all__ = ["EdgarApiConnector"]
