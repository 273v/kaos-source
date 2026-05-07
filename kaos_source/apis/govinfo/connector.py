""":class:`GovInfoApiConnector` — :class:`ApiConnector` for the GovInfo REST API.

Chunk 5 of the kaos-source Track 1 refactor: the connector class only
carries :meth:`metadata` for now. Capability methods (``search``,
``get``) remain free functions in :mod:`kaos_source.apis.govinfo.client`
and are wrapped onto the class in a follow-up chunk.

The class exists so :class:`kaos_source.registry.api_registry.ApiRegistry`
has a stable handle to register, and so callers can introspect
"what does GovInfo support" via ``GovInfoApiConnector.metadata()``.
"""

from __future__ import annotations

from kaos_source.base.api_connector import ApiConnector
from kaos_source.base.capabilities import SourceCapability
from kaos_source.base.metadata import ApiMetadata


class GovInfoApiConnector(ApiConnector):
    """GovInfo (US GPO) public REST API. Requires a free API key from api.data.gov."""

    @classmethod
    def metadata(cls) -> ApiMetadata:
        return ApiMetadata(
            name="govinfo",
            description="US Government Publishing Office REST API — requires API key.",
            base_url="https://api.govinfo.gov",
            requires_auth=True,
            auth_env_var="KAOS_SOURCE_GOVINFO_API_KEY",
            capabilities=(
                SourceCapability.SEARCH,
                SourceCapability.GET,
                SourceCapability.DISCOVER,
            ),
        )


__all__ = ["GovInfoApiConnector"]
