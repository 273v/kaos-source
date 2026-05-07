"""Live E2E tests for forensic/eDiscovery parsers and tools.

Creates real test fixtures (EML with attachments, MBOX, images with EXIF)
and runs the full MCP tool pipeline.

Run with: pytest tests/integration/test_forensics_live.py -v
"""

from __future__ import annotations

import email.mime.base
import email.mime.multipart
import email.mime.text
import re
from pathlib import Path

import pytest
from kaos_core import KaosRuntime

pytestmark = pytest.mark.integration


# ── Test fixtures ───────────────────────────────────────────────────


@pytest.fixture
def sample_eml(tmp_path: Path) -> Path:
    """Create a realistic EML file with HTML body and an attachment."""
    msg = email.mime.multipart.MIMEMultipart("mixed")
    msg["From"] = "Sarah Mitchell <smitchell@harrisonmitchell.com>"
    msg["To"] = "John Doe <jdoe@example.com>, Jane Smith <jsmith@example.com>"
    msg["CC"] = "Legal Team <legal@harrisonmitchell.com>"
    msg["Subject"] = "Re: Settlement Agreement - Case No. 2024-CV-01234"
    msg["Date"] = "Thu, 10 Apr 2025 14:30:00 -0400"
    msg["Message-ID"] = "<abc123@harrisonmitchell.com>"
    msg["In-Reply-To"] = "<xyz789@example.com>"
    msg["References"] = "<first@example.com> <xyz789@example.com>"
    msg["X-Mailer"] = "Microsoft Outlook 16.0"
    msg["Received"] = (
        "from mail.harrisonmitchell.com (mail.harrisonmitchell.com [203.0.113.10]) "
        "by mx.example.com with ESMTPS; Thu, 10 Apr 2025 14:30:05 -0400"
    )
    msg["Received"] = (
        "from [10.0.0.5] (workstation.internal [10.0.0.5]) "
        "by mail.harrisonmitchell.com with ESMTP; Thu, 10 Apr 2025 14:30:01 -0400"
    )
    msg["Authentication-Results"] = (
        "mx.example.com; spf=pass (sender IP is 203.0.113.10) "
        "smtp.mailfrom=harrisonmitchell.com; dkim=pass header.d=harrisonmitchell.com; "
        "dmarc=pass action=none header.from=harrisonmitchell.com"
    )
    msg["Return-Path"] = "<smitchell@harrisonmitchell.com>"

    # Text body
    text_part = email.mime.text.MIMEText(
        "Please find attached the revised settlement agreement.\n\n"
        "Best regards,\nSarah Mitchell, Esq.",
        "plain",
    )
    msg.attach(text_part)

    # HTML body
    html_part = email.mime.text.MIMEText(
        "<html><body><p>Please find attached the <b>revised settlement agreement</b>.</p>"
        "<p>Best regards,<br/>Sarah Mitchell, Esq.</p></body></html>",
        "html",
    )
    msg.attach(html_part)

    # PDF attachment (fake content)
    attachment = email.mime.base.MIMEBase("application", "pdf")
    attachment.set_payload(b"%PDF-1.4 fake content for testing")
    attachment.add_header(
        "Content-Disposition", "attachment", filename="Settlement_Agreement_v3.pdf"
    )
    msg.attach(attachment)

    eml_path = tmp_path / "test_email.eml"
    eml_path.write_text(msg.as_string())
    return eml_path


@pytest.fixture
def sample_mbox(tmp_path: Path, sample_eml: Path) -> Path:
    """Create an MBOX file with multiple messages."""
    mbox_path = tmp_path / "test.mbox"
    eml_content = sample_eml.read_text()

    # Write 3 messages to MBOX format
    with mbox_path.open("w") as f:
        for i in range(3):
            f.write(f"From sender@example.com Thu Apr 10 14:30:0{i} 2025\n")
            f.write(eml_content)
            f.write("\n")

    return mbox_path


@pytest.fixture
def sample_image_with_exif(tmp_path: Path) -> Path:
    """Create a JPEG image with EXIF data using Pillow."""
    try:
        from PIL import Image
        from PIL.ExifTags import Base as ExifBase
    except ImportError:
        pytest.skip("Pillow not installed")

    img = Image.new("RGB", (640, 480), color=(100, 150, 200))
    exif = img.getexif()
    exif[ExifBase.Make] = "Canon"
    exif[ExifBase.Model] = "EOS R5"
    exif[ExifBase.Software] = "Adobe Photoshop 25.0"
    exif[ExifBase.Artist] = "John Photographer"
    exif[ExifBase.Copyright] = "2025 John Photographer"
    exif[ExifBase.DateTime] = "2025:04:10 14:30:00"

    img_path = tmp_path / "test_photo.jpg"
    img.save(img_path, "JPEG", exif=exif.tobytes())
    return img_path


@pytest.fixture
def sample_text_file(tmp_path: Path) -> Path:
    """Create a sample text file."""
    txt = tmp_path / "sample.txt"
    txt.write_text("This is a sample document for eDiscovery testing.\n" * 10)
    return txt


@pytest.fixture
def sample_pdf_file(tmp_path: Path) -> Path:
    """Create a fake PDF file (just magic bytes + content)."""
    pdf = tmp_path / "contract.pdf"
    pdf.write_bytes(b"%PDF-1.4\nFake PDF content for testing checksums\n%%EOF")
    return pdf


# ── Mock runtime ────────────────────────────────────────────────────


def _build_forensic_tools() -> dict:
    from kaos_source.parsers import register_forensics_tools

    runtime = KaosRuntime()
    count = register_forensics_tools(runtime)
    assert count == 5
    return {tool.metadata.name: tool for tool in runtime.tools.list_tool_objects()}


TOOLS = _build_forensic_tools()
TOOL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+){2,}$")


# ── Metadata validation ────────────────────────────────────────────


class TestForensicToolMetadata:
    def test_tool_count(self) -> None:
        assert len(TOOLS) == 5

    def test_expected_names(self) -> None:
        expected = {
            "kaos-source-parse-eml",
            "kaos-source-parse-mbox",
            "kaos-source-email-forensics",
            "kaos-source-image-metadata",
            "kaos-source-file-metadata",
        }
        assert set(TOOLS.keys()) == expected

    @pytest.mark.parametrize("name", list(TOOLS.keys()))
    def test_name_pattern(self, name: str) -> None:
        assert TOOL_NAME_PATTERN.match(name)

    @pytest.mark.parametrize("name", list(TOOLS.keys()))
    def test_annotations_set(self, name: str) -> None:
        ann = TOOLS[name].metadata.annotations
        assert ann is not None
        assert ann.readOnlyHint is True
        assert ann.openWorldHint is False  # All local file operations


# ── EML parser tests ───────────────────────────────────────────────


@pytest.mark.asyncio
class TestParseEmlTool:
    async def test_parse_eml(self, sample_eml: Path) -> None:
        result = await TOOLS["kaos-source-parse-eml"].execute({"path": str(sample_eml)})
        assert not result.isError
        data = result.require_structured()

        # Envelope
        assert data["subject"] == "Re: Settlement Agreement - Case No. 2024-CV-01234"
        assert data["message_id"] == "abc123@harrisonmitchell.com"
        assert data["from_address"]["address"] == "smitchell@harrisonmitchell.com"
        assert data["from_address"]["name"] == "Sarah Mitchell"
        assert len(data["to_addresses"]) == 2
        assert len(data["cc_addresses"]) == 1

        # Threading
        assert data["in_reply_to"] == "xyz789@example.com"
        assert len(data["references"]) == 2

        # Body
        assert data["body_text"] is not None
        assert "settlement agreement" in data["body_text"].lower()
        assert data["body_html"] is not None
        assert "<b>" in data["body_html"]

        # Attachments
        assert data["attachment_count"] == 1
        assert data["attachments"][0]["filename"] == "Settlement_Agreement_v3.pdf"
        assert data["attachments"][0]["content_type"] == "application/pdf"
        assert data["attachments"][0]["md5"] is not None

    async def test_file_not_found(self) -> None:
        result = await TOOLS["kaos-source-parse-eml"].execute({"path": "/nonexistent.eml"})
        assert result.isError


# ── MBOX parser tests ──────────────────────────────────────────────


@pytest.mark.asyncio
class TestParseMboxTool:
    async def test_parse_mbox(self, sample_mbox: Path) -> None:
        result = await TOOLS["kaos-source-parse-mbox"].execute(
            {
                "path": str(sample_mbox),
                "limit": 2,
            }
        )
        assert not result.isError
        data = result.require_structured()
        assert data["message_count"] == 2
        assert len(data["messages"]) == 2
        # Each message should have the same subject
        for msg in data["messages"]:
            assert "Settlement" in msg["subject"]


# ── Email forensics tests ──────────────────────────────────────────


@pytest.mark.asyncio
class TestEmailForensicsTool:
    async def test_forensics_from_file(self, sample_eml: Path) -> None:
        result = await TOOLS["kaos-source-email-forensics"].execute(
            {
                "path": str(sample_eml),
            }
        )
        assert not result.isError
        data = result.require_structured()

        # Received chain
        assert data["hop_count"] >= 2
        assert len(data["received_chain"]) >= 2
        # Most recent hop should reference mx.example.com
        assert any("example.com" in h.get("by_server", "") for h in data["received_chain"])

        # Authentication results
        assert len(data["auth_results"]) >= 2
        mechs = {a["mechanism"] for a in data["auth_results"]}
        assert "spf" in mechs
        assert "dkim" in mechs

        # Return path
        assert data["return_path"] == "smitchell@harrisonmitchell.com"
        # X-Mailer
        assert "Outlook" in data["x_mailer"]


# ── Image metadata tests ──────────────────────────────────────────


@pytest.mark.asyncio
class TestImageMetadataTool:
    async def test_image_with_exif(self, sample_image_with_exif: Path) -> None:
        result = await TOOLS["kaos-source-image-metadata"].execute(
            {
                "path": str(sample_image_with_exif),
            }
        )
        assert not result.isError
        data = result.require_structured()

        assert data["format"] == "JPEG"
        assert data["width"] == 640
        assert data["height"] == 480
        assert data["megapixels"] == 0.31

        # EXIF fields we set
        assert data["camera_make"] == "Canon"
        assert data["camera_model"] == "EOS R5"
        assert data["software"] == "Adobe Photoshop 25.0"
        assert data["artist"] == "John Photographer"
        assert data["copyright"] == "2025 John Photographer"

    async def test_file_not_found(self) -> None:
        result = await TOOLS["kaos-source-image-metadata"].execute({"path": "/nonexistent.jpg"})
        assert result.isError


# ── File metadata tests ────────────────────────────────────────────


@pytest.mark.asyncio
class TestFileMetadataTool:
    async def test_text_file(self, sample_text_file: Path) -> None:
        result = await TOOLS["kaos-source-file-metadata"].execute(
            {
                "path": str(sample_text_file),
            }
        )
        assert not result.isError
        data = result.require_structured()

        assert data["name"] == "sample.txt"
        assert data["extension"] == ".txt"
        assert data["size_bytes"] > 0
        assert data["mime_type"] == "text/plain"
        assert data["md5"] is not None
        assert data["sha256"] is not None
        assert len(data["md5"]) == 32  # MD5 hex length
        assert len(data["sha256"]) == 64  # SHA-256 hex length
        assert data["is_binary"] is False
        assert data["modified_at"] is not None

    async def test_pdf_magic_bytes(self, sample_pdf_file: Path) -> None:
        result = await TOOLS["kaos-source-file-metadata"].execute(
            {
                "path": str(sample_pdf_file),
            }
        )
        assert not result.isError
        data = result.require_structured()
        assert data["name"] == "contract.pdf"
        assert data["mime_type"] == "application/pdf"
        # Magic bytes should start with %PDF (hex 25504446)
        assert data["magic_bytes"].startswith("25504446")

    async def test_checksum_determinism(self, sample_text_file: Path) -> None:
        """Same file should always produce same checksums."""
        tool = TOOLS["kaos-source-file-metadata"]
        r1 = await tool.execute({"path": str(sample_text_file)})
        r2 = await tool.execute({"path": str(sample_text_file)})
        d1 = r1.require_structured()
        d2 = r2.require_structured()
        assert d1["md5"] == d2["md5"]
        assert d1["sha256"] == d2["sha256"]

    async def test_file_not_found(self) -> None:
        result = await TOOLS["kaos-source-file-metadata"].execute({"path": "/nonexistent"})
        assert result.isError
