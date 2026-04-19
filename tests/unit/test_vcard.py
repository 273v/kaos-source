"""Tests for the vCard parser and MCP tool."""

from __future__ import annotations

import re

import pytest
from kaos_core import KaosRuntime

from kaos_source.parsers.vcard import (
    VCardModel,
    VCardParseStatus,
    VCardVersion,
    parse_property_line,
    parse_vcard,
    unfold_lines,
)

# ── Sample VCards ───────────────────────────────────────────────────

SIMPLE_VCARD = """\
BEGIN:VCARD
VERSION:3.0
FN:Jane Doe
N:Doe;Jane;;;
EMAIL;TYPE=work:jane@example.com
TEL;TYPE=work,voice:+1-555-123-4567
ORG:Acme Corp;Legal Department
TITLE:Senior Counsel
END:VCARD
"""

MINIMAL_VCARD = """\
BEGIN:VCARD
VERSION:4.0
FN:John Smith
END:VCARD
"""

COMPLEX_VCARD = """\
BEGIN:VCARD
VERSION:4.0
FN:Dr. Maria García
N:García;Maria;;Dr.;Esq.
EMAIL;TYPE=work:maria@firm.com
EMAIL;TYPE=home:maria@home.com
TEL;TYPE=cell:+1-555-987-6543
TEL;TYPE=work,voice,pref:+1-555-111-2222
ADR;TYPE=work:;;123 Main St;Springfield;IL;62701;US
URL:https://www.firm.com/maria
X-SOCIALPROFILE;TYPE=linkedin:https://www.linkedin.com/in/mariagarcia
ORG:Big Law LLP
TITLE:Partner
BDAY:1975-06-15
NOTE:Specializes in intellectual property law.
CATEGORIES:Attorney,Partner
UID:urn:uuid:abcd-1234
END:VCARD
"""


# ── Parser unit tests ───────────────────────────────────────────────


class TestUnfoldLines:
    def test_simple(self) -> None:
        # RFC 6350: CRLF + space/tab is consumed entirely (space is the fold marker).
        content = "FN:Jane\n Doe"
        lines = unfold_lines(content)
        assert "FN:JaneDoe" in lines

    def test_crlf(self) -> None:
        content = "FN:Jane\r\n Doe"
        lines = unfold_lines(content)
        assert "FN:JaneDoe" in lines

    def test_tab_continuation(self) -> None:
        content = "FN:Jane\n\tDoe"
        lines = unfold_lines(content)
        assert "FN:JaneDoe" in lines

    def test_empty(self) -> None:
        assert unfold_lines("") == []


class TestParsePropertyLine:
    def test_simple(self) -> None:
        prop = parse_property_line("FN:Jane Doe")
        assert prop is not None
        assert prop.name == "FN"
        assert prop.value == "Jane Doe"

    def test_with_params(self) -> None:
        prop = parse_property_line("TEL;TYPE=work,voice:+1-555-1234")
        assert prop is not None
        assert prop.name == "TEL"
        assert prop.value == "+1-555-1234"
        assert "TYPE" in prop.parameters
        assert "work" in prop.parameters["TYPE"]
        assert "voice" in prop.parameters["TYPE"]

    def test_with_group(self) -> None:
        prop = parse_property_line("item1.TEL:+1-555-5678")
        assert prop is not None
        assert prop.group == "item1"
        assert prop.name == "TEL"

    def test_no_colon(self) -> None:
        assert parse_property_line("INVALID LINE") is None


class TestParseVCard:
    def test_simple(self) -> None:
        status, vcard, errors = parse_vcard(SIMPLE_VCARD)
        assert status == VCardParseStatus.SUCCESS
        assert vcard is not None
        assert vcard.formatted_name == "Jane Doe"
        assert vcard.version == VCardVersion.V3_0
        assert vcard.name is not None
        assert vcard.name.family_name == "Doe"
        assert vcard.name.given_name == "Jane"
        assert len(vcard.emails) == 1
        assert vcard.emails[0].address == "jane@example.com"
        assert len(vcard.telephones) == 1
        assert vcard.telephones[0].number == "+1-555-123-4567"
        assert vcard.organization is not None
        assert vcard.organization.name == "Acme Corp"
        assert vcard.organization.units == ["Legal Department"]
        assert vcard.title == "Senior Counsel"
        assert errors == []

    def test_minimal(self) -> None:
        status, vcard, _errors = parse_vcard(MINIMAL_VCARD)
        assert status == VCardParseStatus.SUCCESS
        assert vcard is not None
        assert vcard.formatted_name == "John Smith"
        assert vcard.version == VCardVersion.V4_0

    def test_complex(self) -> None:
        status, vcard, _errors = parse_vcard(COMPLEX_VCARD)
        assert status == VCardParseStatus.SUCCESS
        assert vcard is not None
        assert vcard.formatted_name == "Dr. Maria García"
        assert vcard.name is not None
        assert vcard.name.honorific_prefixes == "Dr."
        assert vcard.name.honorific_suffixes == "Esq."
        assert len(vcard.emails) == 2
        assert len(vcard.telephones) == 2
        assert len(vcard.addresses) == 1
        assert vcard.addresses[0].street_address == "123 Main St"
        assert vcard.addresses[0].locality == "Springfield"
        assert vcard.addresses[0].region == "IL"
        assert vcard.addresses[0].postal_code == "62701"
        assert len(vcard.urls) == 1
        assert len(vcard.social_profiles) == 1
        assert vcard.social_profiles[0].platform == "linkedin"
        assert vcard.birthday is not None
        assert vcard.birthday.year == 1975
        assert vcard.note == "Specializes in intellectual property law."
        assert "Attorney" in vcard.categories
        assert vcard.uid == "urn:uuid:abcd-1234"

    def test_preferred_telephone(self) -> None:
        _status, vcard, _errors = parse_vcard(COMPLEX_VCARD)
        assert vcard is not None
        pref = [t for t in vcard.telephones if t.is_preferred]
        assert len(pref) == 1
        assert pref[0].number == "+1-555-111-2222"

    def test_empty_content(self) -> None:
        status, vcard, _errors = parse_vcard("")
        assert status == VCardParseStatus.INVALID_FORMAT
        assert vcard is None

    def test_missing_begin(self) -> None:
        status, _vcard, _errors = parse_vcard("VERSION:3.0\nFN:Test\nEND:VCARD")
        assert status == VCardParseStatus.INVALID_FORMAT

    def test_missing_fn(self) -> None:
        content = "BEGIN:VCARD\nVERSION:3.0\nEND:VCARD"
        status, vcard, _errors = parse_vcard(content)
        assert status == VCardParseStatus.INVALID_FORMAT
        assert vcard is None

    def test_serialization_roundtrip(self) -> None:
        _status, vcard, _errors = parse_vcard(SIMPLE_VCARD)
        assert vcard is not None
        data = vcard.model_dump(mode="json")
        reconstructed = VCardModel.model_validate(data)
        assert reconstructed.formatted_name == vcard.formatted_name


# ── Tool tests ──────────────────────────────────────────────────────


def _get_vcard_tool():
    from kaos_source.tools_vcard import register_vcard_tools

    runtime = KaosRuntime()
    count = register_vcard_tools(runtime)
    assert count == 1
    return runtime.tools.list_tool_objects()[0]


TOOL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+){2,}$")


class TestVCardToolMetadata:
    def test_name_pattern(self) -> None:
        tool = _get_vcard_tool()
        assert TOOL_NAME_PATTERN.match(tool.metadata.name)

    def test_annotations_set(self) -> None:
        tool = _get_vcard_tool()
        assert tool.metadata.annotations is not None
        assert tool.metadata.annotations.readOnlyHint is True

    def test_module_and_version(self) -> None:
        tool = _get_vcard_tool()
        assert tool.metadata.module_name == "kaos-source"


@pytest.mark.asyncio
class TestVCardParseTool:
    async def test_parse_content(self) -> None:
        tool = _get_vcard_tool()
        result = await tool.execute({"content": SIMPLE_VCARD})
        assert not result.isError
        data = result.require_structured()
        assert data["status"] == "success"
        assert data["vcard"]["formatted_name"] == "Jane Doe"

    async def test_parse_complex(self) -> None:
        tool = _get_vcard_tool()
        result = await tool.execute({"content": COMPLEX_VCARD})
        assert not result.isError
        data = result.require_structured()
        vcard = data["vcard"]
        assert vcard["formatted_name"] == "Dr. Maria García"
        assert len(vcard["emails"]) == 2
        assert len(vcard["telephones"]) == 2

    async def test_parse_file(self, tmp_path) -> None:
        vcf = tmp_path / "test.vcf"
        vcf.write_text(SIMPLE_VCARD, encoding="utf-8")
        tool = _get_vcard_tool()
        result = await tool.execute({"path": str(vcf)})
        assert not result.isError
        data = result.require_structured()
        assert data["vcard"]["formatted_name"] == "Jane Doe"

    async def test_missing_input(self) -> None:
        tool = _get_vcard_tool()
        result = await tool.execute({})
        assert result.isError

    async def test_both_inputs_error(self) -> None:
        tool = _get_vcard_tool()
        result = await tool.execute({"content": SIMPLE_VCARD, "path": "/fake"})
        assert result.isError

    async def test_invalid_content(self) -> None:
        tool = _get_vcard_tool()
        result = await tool.execute({"content": "not a vcard"})
        assert result.isError

    async def test_file_not_found(self) -> None:
        tool = _get_vcard_tool()
        result = await tool.execute({"path": "/nonexistent/file.vcf"})
        assert result.isError
