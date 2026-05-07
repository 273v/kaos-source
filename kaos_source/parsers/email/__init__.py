"""Email parsers — EML, MBOX, and (future) PST/MSG.

Track 1 chunk 6 clusters the email parsers under one subpackage so the
roadmap's PST/MSG ingestion (legal-document-readiness Phase 6) slots
in cleanly alongside the existing :mod:`.eml` / :mod:`.mbox` parsers
without flattening the parsers/ directory further.

Current contents:

- :mod:`kaos_source.parsers.email.eml`     — :func:`parse_eml`,
                                              :func:`parse_eml_file`,
                                              :class:`ParsedEmail` /
                                              :class:`EmailHeaderForensics`
                                              + :class:`EmlParser`
- :mod:`kaos_source.parsers.email.mbox`    — :func:`parse_mbox`,
                                              :class:`MboxResult`
                                              + :class:`MboxParser`
- :mod:`kaos_source.parsers.email.family`  — stub for ``family_id``
                                              correlation across email
                                              + attachments (PST/MSG
                                              ingestion in roadmap
                                              Phase 6)

Old import paths under :mod:`kaos_source.parsers.eml` /
:mod:`kaos_source.parsers.mbox` continue to resolve via back-compat
shims at the old locations.
"""

from __future__ import annotations

from kaos_source.parsers.email.eml import EmlParser
from kaos_source.parsers.email.mbox import MboxParser

__all__ = ["EmlParser", "MboxParser"]
