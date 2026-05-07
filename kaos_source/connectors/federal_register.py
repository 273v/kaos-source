"""Back-compat shim — Federal Register API moved to ``kaos_source.apis.federal_register``.

Track 1 chunk 5 reorganized data-API connectors under
:mod:`kaos_source.apis`. This module re-exports the new public surface
so existing imports keep resolving::

    from kaos_source.connectors.federal_register import (
        KaosSourceFRSettings, search_documents, get_document, get_agencies,
        fetch_document_content, FRDocument, FRSearchResult, FRAgency,
    )

New code should import from :mod:`kaos_source.apis.federal_register`.
"""

from __future__ import annotations

from kaos_source.apis.federal_register.client import (  # noqa: F401
    DOCUMENT_TYPES,
    fetch_document_content,
    get_agencies,
    get_document,
    search_documents,
)
from kaos_source.apis.federal_register.models import (  # noqa: F401
    FRAgency,
    FRDocument,
    FRSearchResult,
)
from kaos_source.settings.federal_register import KaosSourceFRSettings  # noqa: F401
