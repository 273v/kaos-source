"""ISO-8601 timestamp helpers.

Tiny module so callers can ``from kaos_source.runtime.time import now_iso``
without pulling in any of the connector or service hierarchy.
"""

from __future__ import annotations

from datetime import UTC, datetime


def now_iso() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(tz=UTC).isoformat()


def timestamp_to_iso(timestamp: float | None) -> str | None:
    """POSIX timestamp → ISO-8601 string (UTC). ``None`` passes through."""
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()
