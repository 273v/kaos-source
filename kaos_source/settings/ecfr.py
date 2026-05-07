"""Typed settings for the eCFR API connector.

Env vars use the ``KAOS_SOURCE_ECFR_`` prefix:

- ``KAOS_SOURCE_ECFR_TIMEOUT`` — Metadata API timeout (seconds)
- ``KAOS_SOURCE_ECFR_CONTENT_TIMEOUT`` — Content download timeout (seconds, default 300)
- ``KAOS_SOURCE_ECFR_USER_AGENT`` — User-Agent header string

The eCFR API at ``ecfr.gov/api`` is open (no API key required). The
content_timeout default is 300s because large titles (12, 26, 42)
can be slow to render server-side.
"""

from __future__ import annotations

from kaos_core.config.module_settings import ModuleSettings
from pydantic_settings import SettingsConfigDict


class KaosSourceECFRSettings(ModuleSettings):
    """Typed settings for the eCFR connector."""

    timeout: float = 30.0
    content_timeout: float = 300.0  # Large titles (12, 26, 42) can be slow
    user_agent: str = "kaos-source/0.1 (https://273ventures.com)"

    model_config = SettingsConfigDict(
        env_prefix="KAOS_SOURCE_ECFR_",
        env_file=".env",
        extra="ignore",
    )
