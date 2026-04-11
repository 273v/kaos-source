"""Image metadata and EXIF extraction.

Uses Pillow (PIL) for EXIF/GPS extraction.  Falls back to basic image
info (dimensions, format) if Pillow is not available.

Pillow is an optional dependency — install with ``pip install Pillow``.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")


class GpsCoordinates(BaseModel):
    """Decimal GPS coordinates extracted from EXIF."""

    model_config = _STRICT

    latitude: float
    longitude: float
    altitude: float | None = None
    altitude_ref: str | None = Field(None, description="'above_sea_level' or 'below_sea_level'")
    gps_timestamp: str | None = Field(None, description="GPS date/time if present")
    map_url: str | None = Field(None, description="Google Maps link")


class ImageMetadata(BaseModel):
    """Image metadata including EXIF, GPS, and basic properties."""

    model_config = _STRICT

    path: str | None = None
    format: str | None = Field(None, description="JPEG, PNG, TIFF, WEBP, etc.")
    mode: str | None = Field(None, description="RGB, RGBA, L, etc.")
    width: int | None = None
    height: int | None = None
    megapixels: float | None = None

    # EXIF metadata
    camera_make: str | None = None
    camera_model: str | None = None
    software: str | None = None
    datetime_original: str | None = Field(None, description="When the photo was taken")
    datetime_digitized: str | None = Field(None, description="When it was digitized")
    datetime_modified: str | None = Field(None, description="Last modification time")
    artist: str | None = None
    copyright: str | None = None
    orientation: int | None = None
    exposure_time: str | None = None
    f_number: float | None = None
    iso_speed: int | None = None
    focal_length: str | None = None
    flash: str | None = None
    color_space: str | None = None
    image_unique_id: str | None = None
    lens_make: str | None = None
    lens_model: str | None = None

    # GPS
    gps: GpsCoordinates | None = None

    # Raw EXIF for anything we didn't explicitly map
    exif_tags: dict[str, Any] = Field(
        default_factory=dict,
        description="All EXIF tags as human-readable name → value",
    )


# ── GPS conversion ──────────────────────────────────────────────────


def _dms_to_decimal(dms: tuple, ref: str) -> float:
    """Convert EXIF GPS DMS (degrees, minutes, seconds) to decimal."""
    degrees = float(dms[0])
    minutes = float(dms[1])
    seconds = float(dms[2])
    decimal = degrees + minutes / 60 + seconds / 3600
    if ref in ("S", "W"):
        decimal = -decimal
    return round(decimal, 7)


def _extract_gps(gps_info: dict[str, Any]) -> GpsCoordinates | None:
    """Extract GPS coordinates from EXIF GPSInfo dict."""
    lat_dms = gps_info.get("GPSLatitude")
    lat_ref = gps_info.get("GPSLatitudeRef", "N")
    lon_dms = gps_info.get("GPSLongitude")
    lon_ref = gps_info.get("GPSLongitudeRef", "E")

    if not lat_dms or not lon_dms:
        return None

    try:
        lat = _dms_to_decimal(lat_dms, lat_ref)
        lon = _dms_to_decimal(lon_dms, lon_ref)
    except (TypeError, ValueError, IndexError):
        return None

    altitude: float | None = None
    altitude_ref: str | None = None
    if "GPSAltitude" in gps_info:
        try:
            altitude = round(float(gps_info["GPSAltitude"]), 2)
            ref_byte = gps_info.get("GPSAltitudeRef", 0)
            altitude_ref = "below_sea_level" if ref_byte == 1 else "above_sea_level"
        except (TypeError, ValueError):
            pass

    gps_timestamp: str | None = None
    if "GPSDateStamp" in gps_info and "GPSTimeStamp" in gps_info:
        try:
            date = gps_info["GPSDateStamp"]
            time_parts = gps_info["GPSTimeStamp"]
            h, m, s = int(time_parts[0]), int(time_parts[1]), int(time_parts[2])
            gps_timestamp = f"{date.replace(':', '-')}T{h:02d}:{m:02d}:{s:02d}Z"
        except (TypeError, ValueError, IndexError):
            pass

    map_url = f"https://www.google.com/maps?q={lat},{lon}"

    return GpsCoordinates(
        latitude=lat,
        longitude=lon,
        altitude=altitude,
        altitude_ref=altitude_ref,
        gps_timestamp=gps_timestamp,
        map_url=map_url,
    )


# ── EXIF string helpers ─────────────────────────────────────────────


def _safe_str(val: Any) -> str | None:
    """Convert EXIF value to string, handling IFDRational and bytes."""
    if val is None:
        return None
    if isinstance(val, bytes):
        try:
            return val.decode("utf-8", errors="replace").strip("\x00 ")
        except Exception:
            return val.hex()
    return str(val).strip("\x00 ") or None


def _parse_exif_datetime(val: Any) -> str | None:
    """Convert EXIF datetime string '2024:01:15 12:30:00' to ISO 8601."""
    s = _safe_str(val)
    if not s:
        return None
    # EXIF format: YYYY:MM:DD HH:MM:SS
    try:
        return s.replace(":", "-", 2).strip()
    except Exception:
        return s


# ── Main extraction ─────────────────────────────────────────────────


def extract_image_metadata(path: str | Path) -> ImageMetadata:
    """Extract metadata from an image file.

    Uses Pillow for EXIF extraction. Falls back to basic info if
    Pillow cannot read the EXIF data.

    Args:
        path: Path to the image file.

    Returns:
        ImageMetadata with all available fields.
    """
    try:
        from PIL import ExifTags, Image
    except ImportError:
        return ImageMetadata(
            path=str(path),
            exif_tags={"error": "Pillow is required. Install with: pip install Pillow"},
        )

    p = Path(path)

    with Image.open(p) as img:
        # Basic image info
        width, height = img.size
        fmt = img.format
        mode = img.mode
        megapixels = round(width * height / 1_000_000, 2)

        # EXIF data
        exif = img.getexif()
        exif_tags: dict[str, Any] = {}
        mapped: dict[str, Any] = {}

        if exif:
            # Main IFD tags
            for tag_id, value in exif.items():
                tag_name = ExifTags.TAGS.get(tag_id, f"Tag_{tag_id}")
                exif_tags[tag_name] = _safe_str(value) or value

            # EXIF sub-IFD (0x8769) — contains DateTimeOriginal, etc.
            exif_ifd = exif.get_ifd(0x8769)
            if exif_ifd:
                for tag_id, value in exif_ifd.items():
                    tag_name = ExifTags.TAGS.get(tag_id, f"Tag_{tag_id}")
                    exif_tags[tag_name] = _safe_str(value) or value

            # GPS sub-IFD (0x8825)
            gps_ifd = exif.get_ifd(0x8825)
            gps_info: dict[str, Any] = {}
            if gps_ifd:
                for tag_id, value in gps_ifd.items():
                    tag_name = ExifTags.GPSTAGS.get(tag_id, f"GPSTag_{tag_id}")
                    gps_info[tag_name] = value
                    exif_tags[f"GPS.{tag_name}"] = _safe_str(value) or value

            # Map well-known fields
            mapped["camera_make"] = _safe_str(exif_tags.get("Make"))
            mapped["camera_model"] = _safe_str(exif_tags.get("Model"))
            mapped["software"] = _safe_str(exif_tags.get("Software"))
            mapped["datetime_original"] = _parse_exif_datetime(exif_tags.get("DateTimeOriginal"))
            mapped["datetime_digitized"] = _parse_exif_datetime(exif_tags.get("DateTimeDigitized"))
            mapped["datetime_modified"] = _parse_exif_datetime(exif_tags.get("DateTime"))
            mapped["artist"] = _safe_str(exif_tags.get("Artist"))
            mapped["copyright"] = _safe_str(exif_tags.get("Copyright"))
            mapped["orientation"] = exif_tags.get("Orientation")
            mapped["image_unique_id"] = _safe_str(exif_tags.get("ImageUniqueID"))
            mapped["lens_make"] = _safe_str(exif_tags.get("LensMake"))
            mapped["lens_model"] = _safe_str(exif_tags.get("LensModel"))

            # Numeric EXIF fields
            if "ExposureTime" in exif_tags:
                mapped["exposure_time"] = _safe_str(exif_tags["ExposureTime"])
            if "FNumber" in exif_tags:
                with contextlib.suppress(TypeError, ValueError):
                    mapped["f_number"] = round(float(exif_tags["FNumber"]), 1)
            if "ISOSpeedRatings" in exif_tags:
                with contextlib.suppress(TypeError, ValueError):
                    mapped["iso_speed"] = int(exif_tags["ISOSpeedRatings"])
            if "FocalLength" in exif_tags:
                mapped["focal_length"] = _safe_str(exif_tags["FocalLength"])

            # GPS
            gps = _extract_gps(gps_info) if gps_info else None
        else:
            gps = None

    # Build result, filtering None values from mapped
    return ImageMetadata(
        path=str(p),
        format=fmt,
        mode=mode,
        width=width,
        height=height,
        megapixels=megapixels,
        gps=gps,
        exif_tags={k: v for k, v in exif_tags.items() if v is not None},
        **{k: v for k, v in mapped.items() if v is not None},
    )
