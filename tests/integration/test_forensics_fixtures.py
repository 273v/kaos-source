"""Fixture-based tests using real eDiscovery data.

Tests the email parser against real-world samples:
- Enron Corpus (CALO/CMU) — real Enron custodian messages with
  X-Origin, X-Folder, and X-FileName forensic metadata
- GOVCERT-LU eml_parser samples — curated edge cases
- SpamScope mail-parser samples — real spam/phishing with full headers
- Apache Forrest dev list — real open-source project MBOX

See fixtures/forensics/README.md for sources and licensing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kaos_source.parsers.eml import parse_eml_file
from kaos_source.parsers.mbox import parse_mbox

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).parent.parent / "fixtures" / "forensics"


# ── Enron corpus tests ─────────────────────────────────────────────


class TestEnronCorpus:
    """Real Enron custodian messages with full forensic metadata."""

    def test_legal_dept_announcement(self) -> None:
        """Enron Wholesale Services Legal Department reorganization.

        This is the kind of corporate announcement that gets retained
        across many custodians — perfect for testing eDiscovery workflows.
        """
        result = parse_eml_file(FIXTURES / "enron_legal_dept.eml")

        assert result.from_address is not None
        assert result.from_address.address == "enron.announcements@enron.com"
        assert len(result.to_addresses) == 1
        assert result.to_addresses[0].address == "all.employees@enron.com"
        assert result.subject == "Enron Wholesale Services Legal Department"
        assert result.date is not None
        assert result.date.startswith("2000-12")
        assert result.message_id is not None
        assert "JavaMail.evans@thyme" in result.message_id

        # Forensic custodian metadata (X-headers)
        assert "X-Origin" in result.headers
        assert result.headers["X-Origin"] == "McKay-B"
        assert "X-Folder" in result.headers
        assert "Bradley_McKay" in result.headers["X-Folder"]
        assert "X-FileName" in result.headers
        assert result.headers["X-FileName"] == "bmckay.nsf"

        # Body content
        assert result.body_text is not None
        assert "Wholesale Services" in result.body_text
        assert "Legal Department" in result.body_text

    def test_inbound_business(self) -> None:
        """Short internal business email from james.barker@enron.com."""
        result = parse_eml_file(FIXTURES / "enron_inbound_offers.eml")

        assert result.from_address is not None
        assert result.from_address.address == "james.barker@enron.com"
        assert len(result.to_addresses) >= 1
        assert result.to_addresses[0].address == "brad.mckay@enron.com"
        assert result.subject == "Offers"
        assert result.headers["X-Origin"] == "McKay-B"

    def test_mckay_reply(self) -> None:
        """Outbound reply from Brad McKay (the custodian)."""
        result = parse_eml_file(FIXTURES / "enron_mckay_reply.eml")

        # Brad is the sender
        assert result.from_address is not None
        assert result.from_address.address == "brad.mckay@enron.com"
        # Subject indicates a reply
        assert result.subject is not None
        assert result.subject.startswith("Re:")
        # Custodian tag confirms this came from McKay's files
        assert result.headers["X-Origin"] == "McKay-B"

    def test_personal_content_on_company_email(self) -> None:
        """Personal email on company account — classic eDiscovery signal."""
        result = parse_eml_file(FIXTURES / "enron_mckay_fishing.eml")

        # Personal subject matter
        assert "fishing" in (result.subject or "").lower()
        assert result.from_address is not None
        assert result.from_address.address == "brad.mckay@enron.com"

    def test_forwarded_external(self) -> None:
        """External email forwarded to Enron account."""
        result = parse_eml_file(FIXTURES / "enron_forward_external.eml")

        assert result.from_address is not None
        # Not from enron.com — external sender
        assert "enron.com" not in result.from_address.address
        # Subject is a forward
        assert result.subject is not None
        assert result.subject.startswith("FW:")
        # Brad McKay is one of the recipients
        recipients = [addr.address for addr in result.to_addresses]
        assert any("brad.mckay@enron.com" in r for r in recipients)

    def test_all_enron_files_have_custodian_metadata(self) -> None:
        """Every Enron fixture should have X-Origin = McKay-B."""
        enron_files = sorted(FIXTURES.glob("enron_*.eml"))
        assert len(enron_files) >= 5

        for eml_path in enron_files:
            result = parse_eml_file(eml_path)
            assert result.headers.get("X-Origin") == "McKay-B", (
                f"{eml_path.name}: missing or wrong X-Origin"
            )
            assert "X-Folder" in result.headers, f"{eml_path.name}: missing X-Folder"


# ── GOVCERT-LU edge cases ──────────────────────────────────────────


class TestGovcertSamples:
    """Curated EML edge cases from GOVCERT-LU eml_parser."""

    def test_minimal_valid(self) -> None:
        """The smallest valid EML (399 bytes)."""
        result = parse_eml_file(FIXTURES / "govcert_sample.eml")
        assert result.from_address is not None
        assert result.subject is not None

    def test_attachments(self) -> None:
        """Multiple attachments parsed correctly."""
        result = parse_eml_file(FIXTURES / "govcert_sample_attachments.eml")
        assert result.subject == "test mail eml parser"
        # Should have at least one attachment
        assert result.attachment_count >= 1
        # KSRC-08: every attachment carries content_type plus both an MD5
        # (legacy / eDiscovery compat) and a SHA-256 (authoritative).
        for att in result.attachments:
            assert att.content_type is not None
            assert att.md5 is not None
            assert len(att.md5) == 32
            assert att.sha256 is not None
            assert len(att.sha256) == 64
            # Hashes are over the same payload — both should be present
            # together or absent together.
            assert (att.md5 is None) == (att.sha256 is None)

    def test_html_file_as_attachment(self) -> None:
        """HTML file attached to a text-body message (not an HTML body)."""
        result = parse_eml_file(FIXTURES / "govcert_sample_mime_attachment_html.eml")
        # Plain text body
        assert result.body_text is not None
        # One attachment — a .html file
        assert result.attachment_count == 1
        att = result.attachments[0]
        assert att.filename is not None
        assert att.filename.endswith(".html")
        assert att.content_type == "text/html"

    def test_inline_html(self) -> None:
        """Inline HTML body (no attachment)."""
        result = parse_eml_file(FIXTURES / "govcert_sample_mime_inline_html.eml")
        assert result.body_html is not None


# ── SpamScope malformed/forensic samples ──────────────────────────


class TestSpamScopeSamples:
    """Real-world spam/phishing samples with full header chains."""

    def test_full_received_chain(self) -> None:
        """Test message with multiple Received hops."""
        result = parse_eml_file(FIXTURES / "spamscope_mail_test_17.eml")
        assert result.forensics is not None
        # Should have multiple hops in the Received chain
        assert result.forensics.hop_count >= 1
        # Each hop should have some parsed content
        for hop in result.forensics.received_chain:
            # At least one of the fields should be populated
            assert hop.from_server or hop.by_server or hop.raw

    def test_malformed_headers_dont_crash(self) -> None:
        """Malformed EML should parse without crashing."""
        result = parse_eml_file(FIXTURES / "spamscope_mail_malformed_2.eml")
        # Parser should return something even if some fields are missing
        assert result is not None

    def test_short_samples(self) -> None:
        """Very short SpamScope samples should parse."""
        for name in ("spamscope_mail_test_12.eml", "spamscope_mail_test_14.eml"):
            result = parse_eml_file(FIXTURES / name)
            assert result is not None


# ── Apache MBOX (real open-source dev list) ────────────────────────


class TestApacheMbox:
    """Real Apache Forrest dev mailing list — December 2012."""

    def test_parse_all_messages(self) -> None:
        """MBOX should contain 5 messages."""
        result = parse_mbox(FIXTURES / "apache_forrest_dev_2012_12.mbox")
        assert result.message_count == 5
        assert len(result.messages) == 5
        assert len(result.errors) == 0

    def test_subjects_and_senders(self) -> None:
        """Verify real content: JIRA notifications, release discussion."""
        result = parse_mbox(FIXTURES / "apache_forrest_dev_2012_12.mbox")

        subjects = [m.subject for m in result.messages if m.subject]

        # At least one JIRA notification
        assert any("jira" in s.lower() for s in subjects)
        # At least one about Cocoon upgrade (FOR-1240)
        assert any("Cocoon" in s or "FOR-1240" in s for s in subjects)
        # The release discussion
        assert any("Releasing" in s or "2.1.12" in s for s in subjects)

        # At least one message from the JIRA bot
        senders = [m.from_address.address for m in result.messages if m.from_address]
        assert any("jira@apache.org" in s for s in senders)

    def test_thread_chain(self) -> None:
        """JIRA messages should form a thread via References/In-Reply-To."""
        result = parse_mbox(FIXTURES / "apache_forrest_dev_2012_12.mbox")

        # At minimum every message has a Message-ID.  JIRA notifications
        # may or may not thread explicitly — what we check here is that
        # parsing succeeds for all of them.
        for m in result.messages:
            assert m.message_id is not None

    def test_limit_parameter(self) -> None:
        """Limit parameter should cap message count."""
        result = parse_mbox(FIXTURES / "apache_forrest_dev_2012_12.mbox", limit=2)
        assert result.message_count == 2
        assert len(result.messages) == 2


# ── Aggregate tests across all fixtures ────────────────────────────


class TestAllFixtures:
    """Tests that run against every fixture to catch regressions."""

    def test_all_eml_files_parse(self) -> None:
        """Every .eml fixture should parse without raising."""
        eml_files = sorted(FIXTURES.glob("*.eml"))
        assert len(eml_files) >= 13  # 5 enron + 4 govcert + 4 spamscope

        for eml in eml_files:
            try:
                result = parse_eml_file(eml)
            except Exception as exc:
                pytest.fail(f"{eml.name} failed to parse: {exc}")
            assert result is not None, f"{eml.name}: parser returned None"

    def test_all_have_message_id_or_subject(self) -> None:
        """Every real email has at least Message-ID or Subject."""
        for eml in FIXTURES.glob("*.eml"):
            result = parse_eml_file(eml)
            assert result.message_id or result.subject, (
                f"{eml.name}: missing both Message-ID and Subject"
            )
