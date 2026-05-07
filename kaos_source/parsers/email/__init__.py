"""Email parsers — EML, MBOX, and (future) PST/MSG.

Track 1 chunk 6 created this subpackage so the roadmap's PST/MSG
ingestion (legal-document-readiness Phase 6) slots in cleanly
alongside the existing :mod:`.eml` / :mod:`.mbox` parsers without
flattening the parsers/ directory further. Track 1 chunk 8e then
moved the email-related MCP tools (formerly in
``kaos_source/tools_forensics.py``) into :mod:`.tools` for cohesion.

Layout:

- :mod:`.eml`     — :func:`parse_eml`, :func:`parse_eml_file`,
                    :class:`ParsedEmail` + :class:`EmlParser`
- :mod:`.mbox`    — :func:`parse_mbox`, :class:`MboxResult` +
                    :class:`MboxParser`
- :mod:`.family`  — stub for ``family_id`` correlation across email
                    + attachments (PST/MSG ingestion in roadmap
                    Phase 6)
- :mod:`.tools`   — :class:`ParseEmlTool` /
                    :class:`ParseMboxTool` /
                    :class:`EmailForensicsTool` MCP tools +
                    :func:`register_email_tools`

Old import paths under :mod:`kaos_source.parsers.eml` /
:mod:`kaos_source.parsers.mbox` continue to resolve via back-compat
shims at the old locations (kept as 1-line re-export modules).
"""

from __future__ import annotations

from kaos_source.parsers.email.eml import EmlParser
from kaos_source.parsers.email.mbox import MboxParser
from kaos_source.parsers.email.tools import (
    EmailForensicsTool,
    ParseEmlTool,
    ParseMboxTool,
    register_email_tools,
)

__all__ = [
    "EmailForensicsTool",
    "EmlParser",
    "MboxParser",
    "ParseEmlTool",
    "ParseMboxTool",
    "register_email_tools",
]
