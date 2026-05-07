"""Back-compat shim — moved to :mod:`kaos_source.parsers.email.eml` in
Track 1 chunk 6.

Existing ``from kaos_source.parsers.eml import ...`` callers continue
to resolve via the re-exports below. Prefer the new location for new
code:

    from kaos_source.parsers.email.eml import parse_eml, parse_eml_file
"""

from __future__ import annotations

from kaos_source.parsers.email.eml import (  # noqa: F401
    Attachment,
    AuthResult,
    EmailAddress,
    EmailHeaderForensics,
    EmlParser,
    ParsedEmail,
    ReceivedHop,
    parse_eml,
    parse_eml_file,
)
