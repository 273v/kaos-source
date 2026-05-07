"""Email-family correlation helpers — stub for Track 1 chunk 6.

The legal-document-readiness roadmap (Phase 6.3) requires ``family_id``
correlation across email messages and their attachments so Bates
numbering and privilege review can treat the email plus its
attachments as a single document family. Today the EML/MBOX parsers
expose attachments as part of :class:`ParsedEmail`; family_id assignment
is downstream.

PST/MSG support (libratom for PST, extract-msg for MSG — both BSD
compatible per the roadmap) will land in a follow-up chunk and will
emit ``family_id`` on every parsed message + attachment via the
helpers in this module.

For Track 1 chunk 6 this module exists as a placeholder so callers
can ``import kaos_source.parsers.email.family`` without breaking once
the helpers land. The stub functions raise :class:`NotImplementedError`
to keep the absence of behavior loud.
"""

from __future__ import annotations


def assign_family_id(
    message_id: str,
    *,
    parent_message_id: str | None = None,
) -> str:
    """Compute a stable family_id for an email message.

    Will hash the root message-id (or the conversation-thread root for
    replies/forwards) so all members of the family share a single
    identifier suitable for Bates assignment.

    Raises:
        NotImplementedError: implementation lands with PST/MSG support.
    """
    msg = (
        "family_id assignment is not yet implemented; this stub will "
        "be replaced when PST/MSG ingestion lands (roadmap Phase 6)."
    )
    raise NotImplementedError(msg)


def thread_messages(messages: list[object]) -> list[list[object]]:
    """Group a flat list of parsed messages into thread families.

    Implementation will follow JWZ threading + In-Reply-To / References
    fields, with attachments grouped under their parent message.

    Raises:
        NotImplementedError: implementation lands with PST/MSG support.
    """
    msg = (
        "Thread grouping is not yet implemented; this stub will be "
        "replaced when PST/MSG ingestion lands (roadmap Phase 6)."
    )
    raise NotImplementedError(msg)


__all__ = ["assign_family_id", "thread_messages"]
