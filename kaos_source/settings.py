"""Typed settings for kaos-source connectors.

Centralises all ``context.get_config("source_http_...")`` and
``context.get_config("source_browser_...")`` calls into two typed
``ModuleSettings`` subclasses.  Legacy context config keys (e.g.
``source_http_timeout_seconds``) are still honoured via custom
``from_context()`` overrides for backward compatibility.

Usage::

    from kaos_source.settings import KaosSourceHttpSettings, KaosSourceBrowserSettings

    # From environment only
    http_settings = KaosSourceHttpSettings()

    # With KaosContext overrides (highest priority)
    http_settings = KaosSourceHttpSettings.from_context(context, timeout_seconds=60.0)

    # Browser settings
    browser_settings = KaosSourceBrowserSettings.from_context(context)
"""

from __future__ import annotations

from typing import Any, ClassVar, Self

from kaos_core.config.module_settings import ModuleSettings
from pydantic_settings import SettingsConfigDict


class KaosSourceHttpSettings(ModuleSettings):
    """Typed settings for the HTTP source connector.

    Env vars use the ``KAOS_SOURCE_HTTP_`` prefix (e.g.
    ``KAOS_SOURCE_HTTP_TIMEOUT_SECONDS=60``).

    Legacy context config keys (``source_http_timeout_seconds``,
    ``source_http_retry_limit``, etc.) and bare fallback keys
    (``timeout``, ``retry_limit``) are also supported when loading
    via :meth:`from_context`.
    """

    timeout_seconds: float = 30.0
    retry_limit: int = 2
    allowed_hosts: list[str] | None = None
    max_concurrent_per_domain: int = 2
    min_interval_seconds: float = 0.0
    headers: dict[str, str] | None = None
    user_agent: str = "kaos-source/0.1"
    verify_ssl: bool = True
    follow_redirects: bool = True
    http2: bool = False
    retry_initial_delay: float = 0.1
    """Initial retry delay in seconds (exponential backoff base)."""
    retry_max_delay: float = 1.0
    """Maximum retry delay in seconds."""

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


class KaosSourceBrowserSettings(ModuleSettings):
    """Typed settings for the Browser source connector.

    Env vars use the ``KAOS_SOURCE_BROWSER_`` prefix (e.g.
    ``KAOS_SOURCE_BROWSER_HEADLESS=false``).

    Legacy context config keys (``source_browser_headless``,
    ``source_browser_timeout_ms``, etc.) are also supported when
    loading via :meth:`from_context`.
    """

    allowed_hosts: list[str] | None = None
    max_concurrent_per_domain: int = 1
    user_agent: str = "kaos-source-browser/0.1"
    headers: dict[str, str] | None = None
    headless: bool = True
    timeout_ms: int = 30_000
    wait_until: str = "networkidle"
    take_screenshot: bool = True
    screenshot_full_page: bool = True
    ignore_https_errors: bool = False

    model_config = SettingsConfigDict(
        env_prefix="KAOS_SOURCE_BROWSER_",
        env_file=".env",
        extra="ignore",
    )

    @classmethod
    def from_context(cls, context: Any = None, **overrides: Any) -> Self:
        """Create settings from env, overlaid with context config and overrides.

        Checks two layers of context keys:
        1. New-style field names (e.g. ``headless``)
        2. Legacy ``source_browser_`` prefixed keys (e.g. ``source_browser_headless``)
        """
        base = cls()
        context_values: dict[str, Any] = {}
        if context is not None:
            config = getattr(context, "_config", None) or {}
            for field_name in cls.model_fields:
                if field_name in config:
                    context_values[field_name] = config[field_name]
                    continue
                legacy_key = f"source_browser_{field_name}"
                if legacy_key in config:
                    context_values[field_name] = config[legacy_key]
        merged = {**context_values, **overrides}
        if not merged:
            return base
        data = base.model_dump()
        data.update(merged)
        return cls.model_validate(data)
