"""Back-compat shim — SEC EDGAR API moved to ``kaos_source.apis.edgar``.

Track 1 chunk 5 reorganized data-API connectors under
:mod:`kaos_source.apis`. This module re-exports the new public surface
so existing imports keep resolving::

    from kaos_source.connectors.edgar import (
        KaosSourceEdgarSettings, DEFAULT_EDGAR_USER_AGENT,
        search_filings, get_company, lookup_ticker,
        fetch_filing_document, filing_html_to_document,
        EdgarFiling, EdgarSearchResponse, EdgarCompany,
    )

New code should import from :mod:`kaos_source.apis.edgar`.
"""

from __future__ import annotations

from kaos_source.apis.edgar.client import (  # noqa: F401
    FORM_TYPES,
    fetch_filing_document,
    filing_html_to_document,
    get_company,
    lookup_ticker,
    search_filings,
)
from kaos_source.apis.edgar.models import (  # noqa: F401
    EdgarCompany,
    EdgarFiling,
    EdgarSearchResponse,
)
from kaos_source.settings.edgar import (  # noqa: F401
    DEFAULT_EDGAR_USER_AGENT,
    KaosSourceEdgarSettings,
)
