"""Live E2E tests for VCard parsing.

Tests the parser and MCP tool against realistic VCard content:
RFC 6350 examples, real-world messy formats, and edge cases.

Run with: pytest tests/integration/test_vcard_live.py -v
"""

from __future__ import annotations

import pytest

from kaos_source.parsers.vcard import VCardParseStatus, VCardVersion, parse_vcard

pytestmark = pytest.mark.integration


# ── Realistic VCard fixtures ────────────────────────────────────────

# RFC 6350 Section 7.1 — author example
RFC_6350_EXAMPLE = """\
BEGIN:VCARD
VERSION:4.0
FN:Simon Perreault
N:Perreault;Simon;;;ing. jr,M.Sc.
BDAY:--0203
ANNIVERSARY:20090808T1430-0500
GENDER:M
LANG;PREF=1:fr
LANG;PREF=2:en
ORG;TYPE=work:Viagenie
ADR;TYPE=work:;Suite D2-630;2875 Laurier;Quebec;QC;G1V 2M2;Canada
TEL;VALUE=uri;TYPE="work,voice";PREF=1:tel:+1-418-656-9254;ext=102
TEL;VALUE=uri;TYPE="work,cell,voice,video,text":tel:+1-418-262-6501
EMAIL;TYPE=work:simon.perreault@viagenie.ca
GEO;TYPE=work:geo:46.772673,-71.282945
KEY;TYPE=work;VALUE=uri:http://www.viagenie.ca/simon.perreault/simon.asc
TZ;VALUE=utc-offset:-0500
URL;TYPE=home:http://nomis80.org
END:VCARD
"""

# Real-world law firm attorney VCard (common format)
LAW_FIRM_VCARD = """\
BEGIN:VCARD
VERSION:3.0
FN:Sarah J. Mitchell, Esq.
N:Mitchell;Sarah;J.;;Esq.
ORG:Harrison & Mitchell LLP;Litigation Department
TITLE:Senior Partner
TEL;TYPE=WORK,VOICE:+1 (212) 555-0147
TEL;TYPE=WORK,FAX:+1 (212) 555-0148
TEL;TYPE=CELL:+1 (917) 555-0293
EMAIL;TYPE=INTERNET,WORK,PREF:smitchell@harrisonmitchell.com
EMAIL;TYPE=INTERNET,WORK:sarah.mitchell@harrisonmitchell.com
ADR;TYPE=WORK:;;One Liberty Plaza, 35th Floor;New York;NY;10006;United States
URL:https://www.harrisonmitchell.com/attorneys/sarah-mitchell
NOTE:Practice areas: Commercial Litigation, Securities, White Collar Defense
CATEGORIES:Partner,Litigation,Securities
X-SOCIALPROFILE;TYPE=linkedin:https://www.linkedin.com/in/sarahmitchell
END:VCARD
"""

# VCard 2.1 with quoted-printable encoding (older format still in the wild)
VCARD_21_QUOTED_PRINTABLE = """\
BEGIN:VCARD
VERSION:2.1
FN;CHARSET=UTF-8;ENCODING=QUOTED-PRINTABLE:=4D=C3=BCller, Hans
N;CHARSET=UTF-8;ENCODING=QUOTED-PRINTABLE:=4D=C3=BCller;Hans;;;
TEL;WORK;VOICE:+49 30 12345678
TEL;CELL:+49 170 9876543
EMAIL;INTERNET:hans.mueller@example.de
ORG:Rechtsanwaltskanzlei Weber & Partner
TITLE:Rechtsanwalt
ADR;WORK;ENCODING=QUOTED-PRINTABLE:;;Kurf=C3=BCrstendamm 123;Berlin;;10719;Germany
END:VCARD
"""

# VCard with photo data URI (v4.0)
VCARD_WITH_PHOTO = """\
BEGIN:VCARD
VERSION:4.0
FN:Alex Chen
N:Chen;Alex;;;
ORG:TechLaw Inc
TITLE:General Counsel
EMAIL:achen@techlaw.example
TEL;TYPE=work:+1-650-555-0199
PHOTO:data:image/jpeg;base64,/9j/4AAQ
URL:https://techlaw.example/team/alex-chen
X-SOCIALPROFILE;TYPE=linkedin:https://www.linkedin.com/in/alexchen
X-SOCIALPROFILE;TYPE=twitter:https://twitter.com/alexchen
END:VCARD
"""

# Minimal valid VCard (bare minimum per RFC)
MINIMAL_VCARD = """\
BEGIN:VCARD
VERSION:4.0
FN:Test User
END:VCARD
"""

# VCard with multiple addresses and phone types
MULTI_CONTACT_VCARD = """\
BEGIN:VCARD
VERSION:3.0
FN:Maria Garcia-Lopez
N:Garcia-Lopez;Maria;;;
ORG:International Law Group
TITLE:Of Counsel
TEL;TYPE=WORK,VOICE,PREF:+1-305-555-0100
TEL;TYPE=HOME:+1-305-555-0200
TEL;TYPE=CELL:+1-786-555-0300
TEL;TYPE=WORK,FAX:+1-305-555-0101
EMAIL;TYPE=WORK,PREF:mgarcia@ilgroup.com
EMAIL;TYPE=HOME:maria.garcia@personal.example
ADR;TYPE=WORK:;;100 SE 2nd Street, Suite 3200;Miami;FL;33131;US
ADR;TYPE=HOME:;;456 Ocean Drive;Miami Beach;FL;33139;US
URL:https://www.ilgroup.com/team/garcia
CATEGORIES:Attorney,International Law,Immigration
NOTE:Fluent in English\\, Spanish\\, and Portuguese
UID:urn:uuid:12345678-abcd-1234-efgh-123456789012
REV:2024-06-15T10:30:00Z
END:VCARD
"""


# ── Parser tests on realistic data ──────────────────────────────────


class TestRealWorldVCards:
    def test_rfc_6350_example(self) -> None:
        status, vcard, errors = parse_vcard(RFC_6350_EXAMPLE)
        assert status == VCardParseStatus.SUCCESS
        assert vcard is not None
        assert vcard.version == VCardVersion.V4_0
        assert vcard.formatted_name == "Simon Perreault"
        assert vcard.name is not None
        assert vcard.name.family_name == "Perreault"
        assert vcard.name.given_name == "Simon"
        assert vcard.organization is not None
        assert vcard.organization.name == "Viagenie"
        assert len(vcard.telephones) == 2
        assert len(vcard.emails) == 1
        assert "simon.perreault@viagenie.ca" in vcard.emails[0].address
        assert len(vcard.addresses) == 1
        assert vcard.addresses[0].locality == "Quebec"
        assert vcard.addresses[0].country == "Canada"
        assert len(vcard.urls) >= 1
        assert vcard.gender is not None
        assert vcard.gender.sex == "M"

    def test_law_firm_attorney(self) -> None:
        status, vcard, errors = parse_vcard(LAW_FIRM_VCARD)
        assert status == VCardParseStatus.SUCCESS
        assert vcard is not None
        assert "Mitchell" in vcard.formatted_name
        assert vcard.name is not None
        assert vcard.name.honorific_suffixes == "Esq."
        assert vcard.organization is not None
        assert "Harrison" in vcard.organization.name
        assert "Litigation" in vcard.organization.units[0]
        assert vcard.title == "Senior Partner"
        assert len(vcard.telephones) == 3
        assert len(vcard.emails) == 2
        # Check preferred email
        pref = [e for e in vcard.emails if e.is_preferred]
        assert len(pref) == 1
        assert "smitchell" in pref[0].address
        # Address
        assert len(vcard.addresses) == 1
        assert "Liberty Plaza" in vcard.addresses[0].street_address
        assert vcard.addresses[0].region == "NY"
        assert vcard.addresses[0].postal_code == "10006"
        # Social
        assert len(vcard.social_profiles) == 1
        assert vcard.social_profiles[0].platform == "linkedin"
        # Categories
        assert "Partner" in vcard.categories
        assert "Securities" in vcard.categories
        # Note
        assert vcard.note is not None
        assert "Commercial Litigation" in vcard.note

    def test_vcard_21_quoted_printable(self) -> None:
        status, vcard, errors = parse_vcard(VCARD_21_QUOTED_PRINTABLE)
        assert status == VCardParseStatus.SUCCESS
        assert vcard is not None
        # Version 2.1 might not be in our enum — check gracefully
        assert vcard.version in (VCardVersion.V2_1, VCardVersion.UNKNOWN)
        assert vcard.organization is not None
        assert "Weber" in vcard.organization.name
        assert len(vcard.telephones) == 2
        assert len(vcard.addresses) == 1
        # QP-decoded address should contain the German street name
        addr = vcard.addresses[0]
        assert addr.locality == "Berlin"
        assert addr.postal_code == "10719"
        assert addr.country == "Germany"

    def test_vcard_with_photo(self) -> None:
        status, vcard, errors = parse_vcard(VCARD_WITH_PHOTO)
        assert status == VCardParseStatus.SUCCESS
        assert vcard is not None
        assert vcard.formatted_name == "Alex Chen"
        assert vcard.title == "General Counsel"
        assert vcard.photo is not None
        # Photo should be a data URI
        assert vcard.photo.url is not None
        assert vcard.photo.url.startswith("data:image/jpeg")
        # Social profiles
        assert len(vcard.social_profiles) == 2
        platforms = {s.platform for s in vcard.social_profiles}
        assert "linkedin" in platforms
        assert "twitter" in platforms

    def test_minimal_vcard(self) -> None:
        status, vcard, errors = parse_vcard(MINIMAL_VCARD)
        assert status == VCardParseStatus.SUCCESS
        assert vcard is not None
        assert vcard.formatted_name == "Test User"
        assert vcard.emails == []
        assert vcard.telephones == []

    def test_multi_contact(self) -> None:
        status, vcard, errors = parse_vcard(MULTI_CONTACT_VCARD)
        assert status == VCardParseStatus.SUCCESS
        assert vcard is not None
        assert vcard.formatted_name == "Maria Garcia-Lopez"
        # Multiple phones
        assert len(vcard.telephones) == 4
        pref_phones = [t for t in vcard.telephones if t.is_preferred]
        assert len(pref_phones) == 1
        # Multiple emails
        assert len(vcard.emails) == 2
        # Multiple addresses
        assert len(vcard.addresses) == 2
        work_addrs = [a for a in vcard.addresses if any(str(t) == "work" for t in a.types)]
        assert len(work_addrs) == 1
        assert "Miami" in work_addrs[0].locality
        # UID
        assert vcard.uid is not None
        assert "12345678" in vcard.uid
        # Revision
        assert vcard.revision is not None
        assert vcard.revision.year == 2024
        # Categories
        assert "Immigration" in vcard.categories


# ── MCP Tool E2E ───────────────────────────────────────────────────


class _MockToolsRegistry:
    def __init__(self) -> None:
        self.tools: list = []

    def register_tool(self, tool: object) -> None:
        self.tools.append(tool)


class _MockRuntime:
    def __init__(self) -> None:
        self.tools = _MockToolsRegistry()


def _get_vcard_tool():
    from kaos_source.tools_vcard import register_vcard_tools

    rt = _MockRuntime()
    count = register_vcard_tools(rt)
    assert count == 1
    return rt.tools.tools[0]


@pytest.mark.asyncio
class TestVCardToolLive:
    async def test_law_firm_vcard_via_tool(self) -> None:
        tool = _get_vcard_tool()
        result = await tool.execute({"content": LAW_FIRM_VCARD})
        assert not result.isError
        data = result.require_structured()
        assert data["status"] == "success"
        vcard = data["vcard"]
        assert "Mitchell" in vcard["formatted_name"]
        assert vcard["organization"]["name"] == "Harrison & Mitchell LLP"
        assert len(vcard["telephones"]) == 3
        assert len(vcard["emails"]) == 2

    async def test_rfc_example_via_tool(self) -> None:
        tool = _get_vcard_tool()
        result = await tool.execute({"content": RFC_6350_EXAMPLE})
        assert not result.isError
        data = result.require_structured()
        assert data["vcard"]["formatted_name"] == "Simon Perreault"

    async def test_multi_contact_via_tool(self) -> None:
        tool = _get_vcard_tool()
        result = await tool.execute({"content": MULTI_CONTACT_VCARD})
        assert not result.isError
        data = result.require_structured()
        vcard = data["vcard"]
        assert len(vcard["addresses"]) == 2
        assert len(vcard["telephones"]) == 4
        assert "Garcia" in vcard["formatted_name"]

    async def test_file_roundtrip(self, tmp_path) -> None:
        """Write VCard to file, parse via file path."""
        vcf = tmp_path / "attorney.vcf"
        vcf.write_text(LAW_FIRM_VCARD, encoding="utf-8")
        tool = _get_vcard_tool()
        result = await tool.execute({"path": str(vcf)})
        assert not result.isError
        data = result.require_structured()
        assert data["vcard"]["title"] == "Senior Partner"

    async def test_invalid_content_returns_error(self) -> None:
        tool = _get_vcard_tool()
        result = await tool.execute({"content": "This is not a VCard at all."})
        assert result.isError

    async def test_garbled_vcard_returns_error(self) -> None:
        tool = _get_vcard_tool()
        # Has BEGIN/END but no FN
        result = await tool.execute({"content": "BEGIN:VCARD\nVERSION:3.0\nEND:VCARD"})
        assert result.isError
