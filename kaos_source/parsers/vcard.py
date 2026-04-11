"""VCard/VCF parser — RFC 6350 (4.0), RFC 2426 (3.0), and vCard 2.1.

Parses raw vCard text into structured Pydantic models.  No network
access, no database.

Ported from kelvin-legal-intelligence ``services/vcard/parser.py``.
"""

from __future__ import annotations

import contextlib
import quopri
import re
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from kaos_core.logging import get_logger
from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = get_logger(__name__)


# ── Enums ───────────────────────────────────────────────────────────


class VCardVersion(StrEnum):
    """vCard specification version."""

    V2_1 = "2.1"
    V3_0 = "3.0"
    V4_0 = "4.0"
    UNKNOWN = "unknown"


class VCardParseStatus(StrEnum):
    """Result status of vCard parsing."""

    SUCCESS = "success"
    PARTIAL = "partial"
    INVALID_FORMAT = "invalid_format"


class AddressType(StrEnum):
    WORK = "work"
    HOME = "home"
    POSTAL = "postal"
    PARCEL = "parcel"
    DOM = "dom"
    INTL = "intl"
    PREF = "pref"


class TelephoneType(StrEnum):
    WORK = "work"
    HOME = "home"
    CELL = "cell"
    VOICE = "voice"
    FAX = "fax"
    PAGER = "pager"
    TEXT = "text"
    VIDEO = "video"
    TEXTPHONE = "textphone"
    PREF = "pref"


class EmailType(StrEnum):
    WORK = "work"
    HOME = "home"
    INTERNET = "internet"
    PREF = "pref"


# ── Data models ─────────────────────────────────────────────────────

_EXTRA_FORBID = ConfigDict(extra="forbid")


class VCardProperty(BaseModel):
    """A single vCard property with parameters and value."""

    model_config = _EXTRA_FORBID

    name: str
    parameters: dict[str, list[str]] = Field(default_factory=dict)
    value: str
    group: str | None = None


class VCardName(BaseModel):
    model_config = _EXTRA_FORBID

    family_name: str | None = None
    given_name: str | None = None
    additional_names: str | None = None
    honorific_prefixes: str | None = None
    honorific_suffixes: str | None = None


class VCardAddress(BaseModel):
    model_config = _EXTRA_FORBID

    po_box: str | None = None
    extended_address: str | None = None
    street_address: str | None = None
    locality: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country: str | None = None
    types: list[AddressType] = Field(default_factory=list)
    label: str | None = None


class VCardTelephone(BaseModel):
    model_config = _EXTRA_FORBID

    number: str
    types: list[TelephoneType] = Field(default_factory=list)
    is_preferred: bool = False


class VCardEmail(BaseModel):
    model_config = _EXTRA_FORBID

    address: str
    types: list[EmailType] = Field(default_factory=list)
    is_preferred: bool = False


class VCardOrganization(BaseModel):
    model_config = _EXTRA_FORBID

    name: str
    units: list[str] = Field(default_factory=list)


class VCardGender(BaseModel):
    model_config = _EXTRA_FORBID

    sex: str | None = None
    identity: str | None = None


class VCardImage(BaseModel):
    model_config = _EXTRA_FORBID

    url: str | None = None
    media_type: str | None = None
    encoding: str | None = None
    data: str | None = None


class VCardSocialProfile(BaseModel):
    model_config = _EXTRA_FORBID

    url: str
    platform: str | None = None


class VCardModel(BaseModel):
    """Complete parsed vCard."""

    model_config = _EXTRA_FORBID

    version: VCardVersion
    formatted_name: str
    name: VCardName | None = None
    emails: list[VCardEmail] = Field(default_factory=list)
    telephones: list[VCardTelephone] = Field(default_factory=list)
    addresses: list[VCardAddress] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    social_profiles: list[VCardSocialProfile] = Field(default_factory=list)
    organization: VCardOrganization | None = None
    title: str | None = None
    role: str | None = None
    nickname: str | None = None
    birthday: date | None = None
    photo: VCardImage | None = None
    logo: VCardImage | None = None
    gender: VCardGender | None = None
    note: str | None = None
    categories: list[str] = Field(default_factory=list)
    uid: str | None = None
    revision: datetime | None = None
    raw_properties: list[VCardProperty] = Field(default_factory=list)

    @field_validator("emails", "telephones", "addresses", mode="before")
    @classmethod
    def _coerce_none_to_list(cls, v: Any) -> list[Any]:
        return v if v is not None else []


# ── Line-level helpers ──────────────────────────────────────────────


def unfold_lines(content: str) -> list[str]:
    """Unfold wrapped vCard lines per RFC 6350."""
    unfolded = re.sub(r"\r?\n[ \t]", "", content)
    return [line.strip() for line in unfolded.split("\n") if line.strip()]


def parse_property_line(line: str) -> VCardProperty | None:
    """Parse a single vCard property line."""
    colon_idx = line.find(":")
    if colon_idx == -1:
        return None

    prop_part = line[:colon_idx]
    value_part = line[colon_idx + 1 :]

    group: str | None = None
    if "." in prop_part:
        parts = prop_part.split(".", 1)
        if len(parts) == 2:
            group = parts[0]
            prop_part = parts[1]

    segments = prop_part.split(";")
    prop_name = segments[0].upper()
    parameters: dict[str, list[str]] = {}

    for param in segments[1:]:
        if "=" in param:
            pname, pvalue = param.split("=", 1)
            pname = pname.upper()
            pvalues = [v.strip().lower() for v in pvalue.split(",")]
            if pname in parameters:
                parameters[pname].extend(pvalues)
            else:
                parameters[pname] = pvalues

    return VCardProperty(name=prop_name, parameters=parameters, value=value_part, group=group)


# ── Value decoders ──────────────────────────────────────────────────


def _decode_quoted_printable(value: str) -> str:
    try:
        decoded = quopri.decodestring(value.encode("latin-1"))
        try:
            return decoded.decode("utf-8")
        except UnicodeDecodeError:
            return decoded.decode("latin-1")
    except Exception:
        return value


def _parse_structured(value: str) -> list[str]:
    parts = re.split(r"(?<!\\);", value)
    return [p.replace("\\;", ";").strip() for p in parts]


# ── Property parsers ────────────────────────────────────────────────


def _parse_name(prop: VCardProperty) -> VCardName | None:
    parts = _parse_structured(prop.value)
    while len(parts) < 5:
        parts.append("")
    return VCardName(
        family_name=parts[0] or None,
        given_name=parts[1] or None,
        additional_names=parts[2] or None,
        honorific_prefixes=parts[3] or None,
        honorific_suffixes=parts[4] or None,
    )


def _parse_address(prop: VCardProperty) -> VCardAddress | None:
    value = prop.value
    enc = prop.parameters.get("ENCODING", [""])[0].upper()
    if enc in ("QUOTED-PRINTABLE", "QUOTED_PRINTABLE") or (
        "=" in value and re.search(r"=[0-9A-F]{2}", value)
    ):
        value = _decode_quoted_printable(value)

    parts = _parse_structured(value)
    while len(parts) < 7:
        parts.append("")
    parts = [_decode_quoted_printable(p) if "=" in p else p for p in parts]

    types: list[AddressType] = []
    for tv in prop.parameters.get("TYPE", []):
        with contextlib.suppress(ValueError):
            types.append(AddressType(tv.lower()))

    return VCardAddress(
        po_box=parts[0] or None,
        extended_address=parts[1] or None,
        street_address=parts[2] or None,
        locality=parts[3] or None,
        region=parts[4] or None,
        postal_code=parts[5] or None,
        country=parts[6] or None,
        types=types,
    )


def _parse_telephone(prop: VCardProperty) -> VCardTelephone | None:
    types: list[TelephoneType] = []
    is_pref = False
    for tv in prop.parameters.get("TYPE", []):
        tl = tv.lower()
        if tl == "pref":
            is_pref = True
        else:
            with contextlib.suppress(ValueError):
                types.append(TelephoneType(tl))
    return VCardTelephone(number=prop.value, types=types, is_preferred=is_pref)


def _parse_email(prop: VCardProperty) -> VCardEmail | None:
    types: list[EmailType] = []
    is_pref = False
    for tv in prop.parameters.get("TYPE", []):
        tl = tv.lower()
        if tl == "pref":
            is_pref = True
        else:
            with contextlib.suppress(ValueError):
                types.append(EmailType(tl))
    return VCardEmail(address=prop.value, types=types, is_preferred=is_pref)


def _parse_org(prop: VCardProperty) -> VCardOrganization | None:
    parts = _parse_structured(prop.value)
    if not parts or not parts[0]:
        return None
    return VCardOrganization(name=parts[0], units=[u for u in parts[1:] if u])


def _parse_date(value: str) -> date | None:
    value = value.strip()
    if len(value) == 8 and value.isdigit():
        try:
            return datetime.strptime(value, "%Y%m%d").date()
        except ValueError:
            pass
    if len(value) == 10 and value.count("-") == 2:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            pass
    return None


def _parse_timestamp(value: str) -> datetime | None:
    value = value.strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y%m%dT%H%M%SZ",
        "%Y%m%dT%H%M%S",
    ):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _parse_image(prop: VCardProperty) -> VCardImage | None:
    value = prop.value.strip()
    params = prop.parameters

    if value.startswith("data:"):
        try:
            prefix, _data = value.split(",", 1)
            parts = prefix.split(";")
            mtype = parts[0].replace("data:", "").strip()
            enc = "base64" if "base64" in prefix else None
            return VCardImage(url=value, media_type=mtype or None, encoding=enc)
        except (ValueError, IndexError):
            pass

    if value.startswith(("http://", "https://")):
        return VCardImage(url=value, media_type=params.get("MEDIATYPE", [""])[0] or None)

    enc_param = params.get("ENCODING", [""])[0].upper()
    if enc_param in ("B", "BASE64"):
        mtype = None
        if "TYPE" in params:
            tv = params["TYPE"][0].upper()
            mapping = {
                "JPEG": "image/jpeg",
                "JPG": "image/jpeg",
                "PNG": "image/png",
                "GIF": "image/gif",
            }
            mtype = mapping.get(tv, f"image/{tv.lower()}")
        return VCardImage(media_type=mtype, encoding=enc_param, data=value)

    if params.get("VALUE", [""])[0].lower() == "uri":
        return VCardImage(url=value, media_type=params.get("MEDIATYPE", [""])[0] or None)

    if value:
        return VCardImage(data=value)
    return None


def _parse_gender(prop: VCardProperty) -> VCardGender | None:
    parts = prop.value.split(";", 1)
    sex = parts[0].strip() if parts[0] else None
    identity = parts[1].strip() if len(parts) > 1 and parts[1] else None
    if not sex and not identity:
        return None
    return VCardGender(sex=sex, identity=identity)


def _parse_social_profile(prop: VCardProperty) -> VCardSocialProfile | None:
    url = prop.value.strip()
    if not url:
        return None
    platform = None
    if "TYPE" in prop.parameters:
        platform = prop.parameters["TYPE"][0].lower()
    if not platform:
        url_lower = url.lower()
        for domain, name in (
            ("linkedin.com", "linkedin"),
            ("twitter.com", "twitter"),
            ("x.com", "twitter"),
            ("facebook.com", "facebook"),
            ("instagram.com", "instagram"),
            ("github.com", "github"),
        ):
            if domain in url_lower:
                platform = name
                break
    return VCardSocialProfile(url=url, platform=platform)


# ── Main parser ─────────────────────────────────────────────────────

_HANDLED_NAMES = frozenset(
    {
        "VERSION",
        "FN",
        "N",
        "EMAIL",
        "TEL",
        "ADR",
        "URL",
        "ORG",
        "TITLE",
        "ROLE",
        "NICKNAME",
        "BDAY",
        "NOTE",
        "CATEGORIES",
        "UID",
        "PHOTO",
        "LOGO",
        "GENDER",
        "REV",
        "X-SOCIALPROFILE",
    }
)


def parse_vcard(content: str) -> tuple[VCardParseStatus, VCardModel | None, list[str]]:
    """Parse vCard content into a structured model.

    Args:
        content: Raw vCard text (RFC 6350 / RFC 2426 / 2.1).

    Returns:
        Tuple of ``(status, vcard_model, errors)``.
    """
    errors: list[str] = []
    lines = unfold_lines(content)

    if not lines:
        return VCardParseStatus.INVALID_FORMAT, None, ["Empty content"]
    if not any(line.upper() == "BEGIN:VCARD" for line in lines):
        return VCardParseStatus.INVALID_FORMAT, None, ["Missing BEGIN:VCARD"]
    if not any(line.upper() == "END:VCARD" for line in lines):
        return VCardParseStatus.INVALID_FORMAT, None, ["Missing END:VCARD"]

    vcard_lines: list[str] = []
    in_vcard = False
    for line in lines:
        upper = line.upper()
        if upper == "BEGIN:VCARD":
            in_vcard = True
        elif upper == "END:VCARD":
            break
        elif in_vcard:
            vcard_lines.append(line)

    properties: list[VCardProperty] = []
    for line in vcard_lines:
        prop = parse_property_line(line)
        if prop:
            properties.append(prop)

    # Version
    version = VCardVersion.UNKNOWN
    for p in properties:
        if p.name == "VERSION":
            try:
                version = VCardVersion(p.value)
            except ValueError:
                errors.append(f"Unknown vCard version: {p.value}")
            break

    # FN (required)
    fn_props = [p for p in properties if p.name == "FN"]
    if not fn_props:
        return (
            VCardParseStatus.INVALID_FORMAT,
            None,
            ["Missing required FN (formatted name) property"],
        )
    formatted_name = fn_props[0].value

    # Structured name
    name: VCardName | None = None
    n_props = [p for p in properties if p.name == "N"]
    if n_props:
        name = _parse_name(n_props[0])

    # Multi-value properties
    emails = [e for p in properties if p.name == "EMAIL" for e in [_parse_email(p)] if e]
    telephones = [t for p in properties if p.name == "TEL" for t in [_parse_telephone(p)] if t]
    addresses = [a for p in properties if p.name == "ADR" for a in [_parse_address(p)] if a]
    urls = [p.value for p in properties if p.name == "URL"]
    social_profiles = [
        s
        for p in properties
        if p.name == "X-SOCIALPROFILE"
        for s in [_parse_social_profile(p)]
        if s
    ]
    categories: list[str] = []
    for p in properties:
        if p.name == "CATEGORIES":
            categories.extend(c.strip() for c in p.value.split(",") if c.strip())

    # Single-value properties
    def _first(prop_name: str) -> VCardProperty | None:
        for p in properties:
            if p.name == prop_name:
                return p
        return None

    org_prop = _first("ORG")
    organization = _parse_org(org_prop) if org_prop else None
    title = (_first("TITLE") or VCardProperty(name="", value="", parameters={})).value or None
    role = (_first("ROLE") or VCardProperty(name="", value="", parameters={})).value or None
    nickname = (_first("NICKNAME") or VCardProperty(name="", value="", parameters={})).value or None
    note = (_first("NOTE") or VCardProperty(name="", value="", parameters={})).value or None
    uid = (_first("UID") or VCardProperty(name="", value="", parameters={})).value or None

    bday_prop = _first("BDAY")
    birthday = _parse_date(bday_prop.value) if bday_prop else None

    photo_prop = _first("PHOTO")
    photo = _parse_image(photo_prop) if photo_prop else None
    logo_prop = _first("LOGO")
    logo = _parse_image(logo_prop) if logo_prop else None

    gender_prop = _first("GENDER")
    gender = _parse_gender(gender_prop) if gender_prop else None

    rev_prop = _first("REV")
    revision = _parse_timestamp(rev_prop.value) if rev_prop else None

    raw_properties = [p for p in properties if p.name not in _HANDLED_NAMES]

    vcard = VCardModel(
        version=version,
        formatted_name=formatted_name,
        name=name,
        emails=emails,
        telephones=telephones,
        addresses=addresses,
        urls=urls,
        social_profiles=social_profiles,
        organization=organization,
        title=title if title else None,
        role=role if role else None,
        nickname=nickname if nickname else None,
        birthday=birthday,
        photo=photo,
        logo=logo,
        gender=gender,
        note=note if note else None,
        categories=categories,
        uid=uid if uid else None,
        revision=revision,
        raw_properties=raw_properties,
    )

    status = VCardParseStatus.PARTIAL if errors else VCardParseStatus.SUCCESS
    return status, vcard, errors


__all__ = [
    "AddressType",
    "EmailType",
    "TelephoneType",
    "VCardAddress",
    "VCardEmail",
    "VCardGender",
    "VCardImage",
    "VCardModel",
    "VCardName",
    "VCardOrganization",
    "VCardParseStatus",
    "VCardProperty",
    "VCardSocialProfile",
    "VCardTelephone",
    "VCardVersion",
    "parse_vcard",
]
