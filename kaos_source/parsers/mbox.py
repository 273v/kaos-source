"""MBOX email archive parser — pure stdlib, no external deps.

Parses ``.mbox`` files using Python's ``mailbox`` module and delegates
individual message parsing to :mod:`kaos_source.parsers.eml`.
"""

from __future__ import annotations

import mailbox
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from kaos_source.parsers.eml import ParsedEmail, parse_eml

_STRICT = ConfigDict(extra="forbid")


class MboxResult(BaseModel):
    """Result of parsing an MBOX file."""

    model_config = _STRICT

    path: str
    message_count: int = 0
    messages: list[ParsedEmail] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


def parse_mbox(
    path: str | Path,
    *,
    limit: int | None = None,
    include_forensics: bool = True,
) -> MboxResult:
    """Parse an MBOX file into a list of structured messages.

    Args:
        path: Path to .mbox file.
        limit: Max messages to parse (None = all).
        include_forensics: Include header forensic analysis per message.

    Returns:
        MboxResult with parsed messages.
    """
    p = Path(path)
    mbox = mailbox.mbox(str(p))
    messages: list[ParsedEmail] = []
    errors: list[str] = []
    count = 0

    try:
        for i, msg in enumerate(mbox):
            if limit is not None and i >= limit:
                break
            count += 1
            try:
                raw = msg.as_bytes()
                parsed = parse_eml(raw, include_forensics=include_forensics)
                messages.append(parsed)
            except Exception as exc:
                errors.append(f"Message {i}: {exc}")
    finally:
        mbox.close()

    return MboxResult(
        path=str(p),
        message_count=count,
        messages=messages,
        errors=errors,
    )
