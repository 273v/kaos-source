"""Typed settings for the SEC EDGAR API connector.

The SEC requires a descriptive ``User-Agent`` header on all requests.
The default identifies KAOS (``273Ventures research@273ventures.com``)
so live calls succeed out of the box; operators should override via
``KAOS_SOURCE_EDGAR_USER_AGENT`` (or legacy ``SEC_EDGAR_USER_AGENT``)
with their own ``"YourCompany email@company.com"``.

Env vars use the ``KAOS_SOURCE_EDGAR_`` prefix; ``SEC_EDGAR_USER_AGENT``
is honored for backward compatibility via a ``mode="before"`` validator.
"""

from __future__ import annotations

import os
from typing import Any

from kaos_core.config.module_settings import ModuleSettings
from pydantic import model_validator
from pydantic_settings import SettingsConfigDict

DEFAULT_EDGAR_USER_AGENT = "273Ventures research@273ventures.com"


class KaosSourceEdgarSettings(ModuleSettings):
    """Typed settings for the EDGAR connector."""

    user_agent: str = DEFAULT_EDGAR_USER_AGENT
    timeout: float = 30.0

    model_config = SettingsConfigDict(
        env_prefix="KAOS_SOURCE_EDGAR_",
        env_file=".env",
        extra="ignore",
    )

    @model_validator(mode="before")
    @classmethod
    def _legacy_env_fallback(cls, values: dict[str, Any]) -> dict[str, Any]:
        if not values.get("user_agent"):
            legacy = os.environ.get("SEC_EDGAR_USER_AGENT")
            if legacy:
                values["user_agent"] = legacy
        return values

    def require_user_agent(self) -> str:
        """Return the user-agent string, raising a clear error if not configured.

        The SEC requires an honest User-Agent header identifying your
        organization and contact email on all EDGAR requests.
        """
        if not self.user_agent:
            msg = (
                "SEC EDGAR requires a User-Agent header identifying your organization "
                "and contact email (e.g. 'YourCompany contact@company.com'). "
                "Set the KAOS_SOURCE_EDGAR_USER_AGENT environment variable "
                "(or legacy SEC_EDGAR_USER_AGENT). "
                "See https://www.sec.gov/os/accessing-edgar-data for details."
            )
            raise ValueError(msg)
        return self.user_agent
