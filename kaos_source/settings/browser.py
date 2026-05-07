"""Typed settings for the Browser source connector.

Env vars use the ``KAOS_SOURCE_BROWSER_`` prefix (e.g.
``KAOS_SOURCE_BROWSER_HEADLESS=false``).

Legacy context config keys (``source_browser_headless``,
``source_browser_timeout_ms``, etc.) are also supported when
loading via :meth:`from_context`.
"""

from __future__ import annotations

from typing import Any, Self

from kaos_core.config.module_settings import ModuleSettings
from pydantic_settings import SettingsConfigDict


class KaosSourceBrowserSettings(ModuleSettings):
    """Typed settings for the Browser source connector."""

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
