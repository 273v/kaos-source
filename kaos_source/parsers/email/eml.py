"""EML/MIME email parser — pure stdlib, no external deps.

Parses ``.eml`` files (RFC 5322 / MIME) into structured models using
Python's ``email.parser`` module.  Extracts headers, body (text and HTML),
attachments, and threading metadata.

Also provides header-level forensic analysis: Received chain parsing,
authentication results (SPF/DKIM/DMARC), and routing analysis.
"""

from __future__ import annotations

import contextlib
import email
import email.policy
import email.utils
import hashlib
import re
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from kaos_core.logging import get_logger
from pydantic import BaseModel, ConfigDict, Field

logger = get_logger(__name__)

_STRICT = ConfigDict(extra="forbid")


# ── Models ──────────────────────────────────────────────────────────


class EmailAddress(BaseModel):
    """Parsed email address with optional display name."""

    model_config = _STRICT

    name: str | None = None
    address: str


class Attachment(BaseModel):
    """Email attachment metadata (content not included by default)."""

    model_config = _STRICT

    filename: str | None = None
    content_type: str
    size: int | None = None
    content_id: str | None = Field(None, description="For inline images (CID)")
    md5: str | None = Field(
        None,
        description=(
            "MD5 of the decoded payload. Retained for eDiscovery / forensic "
            "tooling compatibility (Enron NSRL, EnCase, Magnet); not "
            "cryptographically authoritative — pair with `sha256` for any "
            "integrity claim."
        ),
    )
    sha256: str | None = Field(
        None,
        description=(
            "SHA-256 of the decoded payload. Authoritative integrity field "
            "(KSRC-08). Computed alongside `md5` so legacy eDiscovery "
            "consumers continue to work without changes."
        ),
    )


class ReceivedHop(BaseModel):
    """A single hop in the Received header chain."""

    model_config = _STRICT

    from_server: str | None = None
    by_server: str | None = None
    via: str | None = None
    with_protocol: str | None = None
    timestamp: str | None = Field(None, description="ISO 8601")
    raw: str


class AuthResult(BaseModel):
    """SPF/DKIM/DMARC result from Authentication-Results header."""

    model_config = _STRICT

    mechanism: str = Field(description="spf, dkim, or dmarc")
    result: str = Field(description="pass, fail, softfail, none, etc.")
    detail: str | None = None


class EmailHeaderForensics(BaseModel):
    """Forensic analysis of email headers."""

    model_config = _STRICT

    received_chain: list[ReceivedHop] = Field(default_factory=list)
    auth_results: list[AuthResult] = Field(default_factory=list)
    return_path: str | None = None
    x_mailer: str | None = None
    x_originating_ip: str | None = None
    user_agent: str | None = None
    hop_count: int = 0
    transit_time_seconds: float | None = Field(
        None, description="Time between first and last Received hop"
    )


class ParsedEmail(BaseModel):
    """Complete parsed email message."""

    model_config = _STRICT

    # Envelope
    message_id: str | None = None
    subject: str | None = None
    date: str | None = Field(None, description="ISO 8601")
    from_address: EmailAddress | None = None
    to_addresses: list[EmailAddress] = Field(default_factory=list)
    cc_addresses: list[EmailAddress] = Field(default_factory=list)
    bcc_addresses: list[EmailAddress] = Field(default_factory=list)
    reply_to: EmailAddress | None = None

    # Threading
    in_reply_to: str | None = None
    references: list[str] = Field(default_factory=list)

    # Body
    body_text: str | None = None
    body_html: str | None = None

    # Attachments
    attachments: list[Attachment] = Field(default_factory=list)
    attachment_count: int = 0

    # Forensics
    forensics: EmailHeaderForensics | None = None

    # Metadata
    headers: dict[str, str] = Field(
        default_factory=dict, description="All headers (first occurrence)"
    )


# ── Address parsing ─────────────────────────────────────────────────


def _parse_address(raw: str | None) -> EmailAddress | None:
    if not raw:
        return None
    name, addr = email.utils.parseaddr(raw)
    if not addr:
        return None
    return EmailAddress(name=name or None, address=addr)


def _parse_address_list(raw: str | None) -> list[EmailAddress]:
    if not raw:
        return []
    pairs = email.utils.getaddresses([raw])
    return [EmailAddress(name=n or None, address=a) for n, a in pairs if a]


# ── Date parsing ────────────────────────────────────────────────────


def _parse_date(raw: str | None) -> str | None:
    if not raw:
        return None
    parsed = email.utils.parsedate_to_datetime(raw)
    if parsed:
        return parsed.isoformat()
    return None


# ── Received chain parsing ──────────────────────────────────────────

_FROM_RE = re.compile(r"from\s+(\S+)", re.IGNORECASE)
_BY_RE = re.compile(r"by\s+(\S+)", re.IGNORECASE)
_VIA_RE = re.compile(r"via\s+(\S+)", re.IGNORECASE)
_WITH_RE = re.compile(r"with\s+(\S+)", re.IGNORECASE)
_DATE_RE = re.compile(r";\s*(.+)$")


def _parse_received(raw: str) -> ReceivedHop:
    """Parse a single Received header value."""
    from_match = _FROM_RE.search(raw)
    by_match = _BY_RE.search(raw)
    via_match = _VIA_RE.search(raw)
    with_match = _WITH_RE.search(raw)
    date_match = _DATE_RE.search(raw)

    timestamp = None
    if date_match:
        try:
            dt = email.utils.parsedate_to_datetime(date_match.group(1).strip())
            timestamp = dt.isoformat()
        except Exception:
            pass

    return ReceivedHop(
        from_server=from_match.group(1) if from_match else None,
        by_server=by_match.group(1) if by_match else None,
        via=via_match.group(1) if via_match else None,
        with_protocol=with_match.group(1) if with_match else None,
        timestamp=timestamp,
        raw=raw.strip(),
    )


# ── Auth results parsing ───────────────────────────────────────────

_AUTH_RE = re.compile(
    r"(spf|dkim|dmarc)\s*=\s*(\w+)(?:\s+\(([^)]*)\))?",
    re.IGNORECASE,
)


def _parse_auth_results(raw: str) -> list[AuthResult]:
    """Parse Authentication-Results header."""
    results: list[AuthResult] = []
    for match in _AUTH_RE.finditer(raw):
        results.append(
            AuthResult(
                mechanism=match.group(1).lower(),
                result=match.group(2).lower(),
                detail=match.group(3) if match.group(3) else None,
            )
        )
    return results


# ── Body extraction ─────────────────────────────────────────────────


def _extract_body(msg: EmailMessage) -> tuple[str | None, str | None]:
    """Extract text and HTML body from a MIME message."""
    text_body: str | None = None
    html_body: str | None = None

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            disp = str(part.get("Content-Disposition", ""))
            if "attachment" in disp:
                continue
            if ct == "text/plain" and text_body is None:
                payload = part.get_content()
                if isinstance(payload, str):
                    text_body = payload
                elif isinstance(payload, bytes):
                    text_body = payload.decode("utf-8", errors="replace")
            elif ct == "text/html" and html_body is None:
                payload = part.get_content()
                if isinstance(payload, str):
                    html_body = payload
                elif isinstance(payload, bytes):
                    html_body = payload.decode("utf-8", errors="replace")
    else:
        ct = msg.get_content_type()
        payload = msg.get_content()
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8", errors="replace")
        if isinstance(payload, str):
            if ct == "text/html":
                html_body = payload
            else:
                text_body = payload

    return text_body, html_body


# ── Attachment extraction ───────────────────────────────────────────


def _extract_attachments(msg: EmailMessage) -> list[Attachment]:
    """Extract attachment metadata (not content) from a MIME message."""
    attachments: list[Attachment] = []

    for part in msg.walk():
        disp = str(part.get("Content-Disposition", ""))
        ct = part.get_content_type()

        # Skip multipart containers and inline text bodies
        if part.get_content_maintype() == "multipart":
            continue
        if ct in ("text/plain", "text/html") and "attachment" not in disp:
            continue

        filename = part.get_filename()
        if not filename and "attachment" not in disp:
            continue

        content_id = part.get("Content-ID")
        if content_id:
            content_id = content_id.strip("<>")

        # Get content for size + hashes. KSRC-08: SHA-256 is authoritative;
        # MD5 retained for eDiscovery tool compat (not a security claim —
        # ``usedforsecurity=False`` documents that and keeps Bandit B324
        # quiet).
        payload = part.get_payload(decode=True)
        if isinstance(payload, bytes):
            size: int | None = len(payload)
            md5: str | None = hashlib.md5(payload, usedforsecurity=False).hexdigest()
            sha256: str | None = hashlib.sha256(payload).hexdigest()
        else:
            size = None
            md5 = None
            sha256 = None

        attachments.append(
            Attachment(
                filename=filename,
                content_type=ct,
                size=size,
                content_id=content_id,
                md5=md5,
                sha256=sha256,
            )
        )

    return attachments


# ── Header forensics ───────────────────────────────────────────────


def _analyze_forensics(msg: EmailMessage) -> EmailHeaderForensics:
    """Analyze email headers for forensic information."""
    # Received chain (in reverse order — most recent first)
    received_headers = msg.get_all("Received", [])
    hops = [_parse_received(r) for r in received_headers]

    # Transit time between first and last hop
    transit_time: float | None = None
    hop_timestamps: list[datetime] = []
    for hop in hops:
        if hop.timestamp:
            with contextlib.suppress(ValueError):
                hop_timestamps.append(datetime.fromisoformat(hop.timestamp))
    if len(hop_timestamps) >= 2:
        # First received = latest, last received = earliest
        transit_time = (hop_timestamps[0] - hop_timestamps[-1]).total_seconds()

    # Authentication results
    auth_results: list[AuthResult] = []
    for ar_header in msg.get_all("Authentication-Results", []):
        auth_results.extend(_parse_auth_results(ar_header))

    return EmailHeaderForensics(
        received_chain=hops,
        auth_results=auth_results,
        return_path=msg.get("Return-Path", "").strip("<>") or None,
        x_mailer=msg.get("X-Mailer"),
        x_originating_ip=msg.get("X-Originating-IP", "").strip("[]") or None,
        user_agent=msg.get("User-Agent"),
        hop_count=len(hops),
        transit_time_seconds=round(transit_time, 2) if transit_time is not None else None,
    )


# ── Main parser ─────────────────────────────────────────────────────


def parse_eml(
    content: str | bytes,
    *,
    include_forensics: bool = True,
) -> ParsedEmail:
    """Parse an EML/MIME message into structured data.

    Args:
        content: Raw EML content (string or bytes).
        include_forensics: Include header forensic analysis.

    Returns:
        ParsedEmail with all extracted fields.
    """
    if isinstance(content, str):
        msg = email.message_from_string(content, policy=email.policy.default)
    else:
        msg = email.message_from_bytes(content, policy=email.policy.default)

    # Body
    text_body, html_body = _extract_body(msg)

    # Attachments
    attachments = _extract_attachments(msg)

    # References (space or newline separated message IDs)
    refs_raw = msg.get("References", "")
    references = [r.strip() for r in refs_raw.split() if r.strip()]

    # All headers (first occurrence)
    headers: dict[str, str] = {}
    for key in msg:
        if key not in headers:
            headers[key] = str(msg[key])

    # Forensics
    forensics = _analyze_forensics(msg) if include_forensics else None

    return ParsedEmail(
        message_id=msg.get("Message-ID", "").strip("<>") or None,
        subject=msg.get("Subject"),
        date=_parse_date(msg.get("Date")),
        from_address=_parse_address(msg.get("From")),
        to_addresses=_parse_address_list(msg.get("To")),
        cc_addresses=_parse_address_list(msg.get("CC")),
        bcc_addresses=_parse_address_list(msg.get("BCC")),
        reply_to=_parse_address(msg.get("Reply-To")),
        in_reply_to=msg.get("In-Reply-To", "").strip("<>") or None,
        references=references,
        body_text=text_body,
        body_html=html_body,
        attachments=attachments,
        attachment_count=len(attachments),
        forensics=forensics,
        headers=headers,
    )


def parse_eml_file(path: str | Path) -> ParsedEmail:
    """Parse an EML file from disk.

    Args:
        path: Path to .eml file.

    Returns:
        ParsedEmail with all extracted fields.
    """
    p = Path(path)
    content = p.read_bytes()
    return parse_eml(content)


# ---------------------------------------------------------------------------
# SourceParser conformance (Track 1 chunk 6)
# ---------------------------------------------------------------------------


from kaos_source.base.capabilities import SourceCapability  # noqa: E402
from kaos_source.base.metadata import ParserMetadata  # noqa: E402
from kaos_source.base.parser import SourceParser  # noqa: E402


class EmlParser(SourceParser):
    """:class:`SourceParser` wrapper for :func:`parse_eml` / :func:`parse_eml_file`.

    Holds identity metadata + MIME-type advertisement so the parser can
    be discovered via :class:`ParserRegistry`. Decoding is delegated to
    the module-level functions.
    """

    @classmethod
    def metadata(cls) -> ParserMetadata:
        return ParserMetadata(
            name="eml",
            description="EML/MIME email parser (RFC 5322) with header forensics.",
            supported_mime_types=("message/rfc822",),
            supported_extensions=(".eml",),
            capabilities=(SourceCapability.PARSE,),
        )

    @property
    def supported_mime_types(self) -> tuple[str, ...]:
        return ("message/rfc822",)

    def parse(
        self,
        payload: bytes | str | Path,
        *,
        include_forensics: bool = True,
    ) -> ParsedEmail:
        if isinstance(payload, Path):
            return parse_eml_file(payload)
        return parse_eml(payload, include_forensics=include_forensics)
