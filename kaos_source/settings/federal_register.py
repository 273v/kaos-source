"""Typed settings for the Federal Register API connector.

Env vars use the ``KAOS_SOURCE_FR_`` prefix:

- ``KAOS_SOURCE_FR_TIMEOUT`` — API metadata request timeout (seconds)
- ``KAOS_SOURCE_FR_CONTENT_TIMEOUT`` — Content download timeout (seconds)
- ``KAOS_SOURCE_FR_USER_AGENT`` — User-Agent header string

The Federal Register API at ``federalregister.gov/api/v1`` is open
(no API key required); the User-Agent is courtesy / debugging only.
"""

from __future__ import annotations

from kaos_core.config.module_settings import ModuleSettings
from pydantic_settings import SettingsConfigDict


class KaosSourceFRSettings(ModuleSettings):
    """Typed settings for the Federal Register connector."""

    timeout: float = 30.0
    content_timeout: float = 120.0
    user_agent: str = "kaos-source/0.1 (https://273ventures.com)"

    model_config = SettingsConfigDict(
        env_prefix="KAOS_SOURCE_FR_",
        env_file=".env",
        extra="ignore",
    )
