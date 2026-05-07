"""Typed settings for the GovInfo API connector.

Env vars use the ``KAOS_SOURCE_GOVINFO_`` prefix:

- ``KAOS_SOURCE_GOVINFO_API_KEY`` — GovInfo API key (required, ``SecretStr``)
- ``KAOS_SOURCE_GOVINFO_TIMEOUT`` — API request timeout (seconds)
- ``KAOS_SOURCE_GOVINFO_USER_AGENT`` — User-Agent header string

Legacy env var ``GOVINFO_API_KEY`` is honored for backward compatibility
via a ``mode="before"`` validator.

Free API key: https://api.data.gov/signup/
"""

from __future__ import annotations

import os
from typing import Any

from kaos_core.config.module_settings import ModuleSettings
from pydantic import SecretStr, model_validator
from pydantic_settings import SettingsConfigDict


class KaosSourceGovInfoSettings(ModuleSettings):
    """Typed settings for the GovInfo connector."""

    api_key: SecretStr | None = None
    timeout: float = 30.0
    user_agent: str = "kaos-source/0.1 (https://273ventures.com)"

    model_config = SettingsConfigDict(
        env_prefix="KAOS_SOURCE_GOVINFO_",
        env_file=".env",
        extra="ignore",
    )

    @model_validator(mode="before")
    @classmethod
    def _legacy_env_fallback(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Support legacy GOVINFO_API_KEY env var."""
        if not values.get("api_key"):
            legacy = os.environ.get("GOVINFO_API_KEY")
            if legacy:
                values["api_key"] = legacy
        return values

    def get_api_key(self) -> str:
        """Get the API key or raise a clear error."""
        if self.api_key is not None:
            return self.api_key.get_secret_value()
        msg = (
            "GovInfo API key not set. "
            "Set KAOS_SOURCE_GOVINFO_API_KEY or GOVINFO_API_KEY env var. "
            "Get a free key at https://api.data.gov/signup/"
        )
        raise ValueError(msg)
