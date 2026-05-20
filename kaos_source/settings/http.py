"""Typed settings for the HTTP source connector.

Env vars use the ``KAOS_SOURCE_HTTP_`` prefix (e.g.
``KAOS_SOURCE_HTTP_TIMEOUT_SECONDS=60``).

Legacy context config keys (``source_http_timeout_seconds``,
``source_http_retry_limit``, etc.) and bare fallback keys
(``timeout``, ``retry_limit``) are also supported when loading
via :meth:`from_context`.
"""

from __future__ import annotations

from typing import Any, ClassVar, Self

from kaos_core.config.module_settings import ModuleSettings
from pydantic_settings import SettingsConfigDict

# Realistic desktop Chrome UA used by default so hosts that block
# obvious bot UA strings (``python-httpx``, ``kaos-source/0.1``) still
# serve the page. Issue #444 — anti-bot fetch hardening.
#
# Keep this in sync with the Chrome stable channel roughly each major
# release; lying outright (e.g. claiming Chrome 200) defeats the point
# and can trigger different anti-bot rules.
DEFAULT_HTTP_UA: str = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

# Browser-shaped Accept / Accept-Language / Sec-Fetch-* defaults paired
# with the realistic UA. Hosts that gate on UA alone are usually
# happy with just the UA, but a meaningful chunk also gate on header
# presence (Reuters, Bloomberg) — sending these by default reduces
# the surface area where the Playwright fallback has to fire.
DEFAULT_BROWSER_HEADERS: dict[str, str] = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Upgrade-Insecure-Requests": "1",
}


class KaosSourceHttpSettings(ModuleSettings):
    """Typed settings for the HTTP source connector."""

    timeout_seconds: float = 30.0
    retry_limit: int = 2
    allowed_hosts: list[str] | None = None
    max_concurrent_per_domain: int = 2
    min_interval_seconds: float = 0.0
    headers: dict[str, str] | None = None
    user_agent: str = DEFAULT_HTTP_UA
    verify_ssl: bool = True
    follow_redirects: bool = True
    http2: bool = False
    retry_initial_delay: float = 0.1
    """Initial retry delay in seconds (exponential backoff base)."""
    retry_max_delay: float = 1.0
    """Maximum retry delay in seconds."""

    domain_overrides: dict[str, dict[str, str]] | None = None
    """Per-domain header overrides (issue #444).

    Keys are host suffixes matched against the request URL's hostname
    (e.g. ``"reuters.com"`` matches ``www.reuters.com``). Values are
    header name/value mappings that are merged on top of the
    connector's defaults for matching hosts. Use this to set a more
    specific User-Agent, Accept-Language, or custom auth header for
    a host that needs special treatment.

    Example::

        KaosSourceHttpSettings(
            domain_overrides={
                "reuters.com": {
                    "User-Agent": "Mozilla/5.0 ... Chrome/131 ...",
                    "Accept": "text/html",
                },
                "sec.gov": {
                    "User-Agent": "Acme Research research@example.com",
                },
            }
        )
    """

    enable_browser_fallback: bool = True
    """When True, the FetchURL tool falls back to Playwright on anti-bot challenges."""

    model_config = SettingsConfigDict(
        env_prefix="KAOS_SOURCE_HTTP_",
        env_file=".env",
        extra="ignore",
    )

    # Bare fallback keys used in the old connector code
    _BARE_FALLBACK_KEYS: ClassVar[dict[str, str]] = {
        "timeout_seconds": "timeout",
        "retry_limit": "retry_limit",
    }

    @classmethod
    def from_context(cls, context: Any = None, **overrides: Any) -> Self:
        """Create settings from env, overlaid with context config and overrides.

        Checks three layers of context keys in order:
        1. New-style field names (e.g. ``timeout_seconds``)
        2. Legacy ``source_http_`` prefixed keys (e.g. ``source_http_timeout_seconds``)
        3. Bare fallback keys (e.g. ``timeout``)
        """
        base = cls()
        context_values: dict[str, Any] = {}
        if context is not None:
            config = getattr(context, "_config", None) or {}
            for field_name in cls.model_fields:
                # New-style: field name directly in config
                if field_name in config:
                    context_values[field_name] = config[field_name]
                    continue
                # Legacy: source_http_ prefixed key
                legacy_key = f"source_http_{field_name}"
                if legacy_key in config:
                    context_values[field_name] = config[legacy_key]
                    continue
                # Bare fallback (e.g. "timeout" -> "timeout_seconds")
                bare_key = cls._BARE_FALLBACK_KEYS.get(field_name)
                if bare_key is not None and bare_key in config:
                    context_values[field_name] = config[bare_key]
        merged = {**context_values, **overrides}
        if not merged:
            return base
        data = base.model_dump()
        data.update(merged)
        return cls.model_validate(data)
