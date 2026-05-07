"""Typed module settings for kaos-source connectors.

Centralised under ``settings/`` (Track 1 chunk 3) — one file per
:class:`ModuleSettings` subclass. Pre-chunk-3 these were split between
``kaos_source/settings.py`` (HTTP, Browser) and per-connector modules
in ``kaos_source/connectors/`` (FR, eCFR, EDGAR, GovInfo); now they
live here, single source of truth.

Public API preserved: ``from kaos_source.settings import
KaosSourceHttpSettings`` continues to resolve via this re-export.
Connector modules also re-export their own settings class for
back-compat (``from kaos_source.connectors.federal_register import
KaosSourceFRSettings`` still works).
"""

from __future__ import annotations

from kaos_source.settings.browser import KaosSourceBrowserSettings
from kaos_source.settings.ecfr import KaosSourceECFRSettings
from kaos_source.settings.edgar import (
    DEFAULT_EDGAR_USER_AGENT,
    KaosSourceEdgarSettings,
)
from kaos_source.settings.federal_register import KaosSourceFRSettings
from kaos_source.settings.govinfo import KaosSourceGovInfoSettings
from kaos_source.settings.http import KaosSourceHttpSettings

__all__ = [
    "DEFAULT_EDGAR_USER_AGENT",
    "KaosSourceBrowserSettings",
    "KaosSourceECFRSettings",
    "KaosSourceEdgarSettings",
    "KaosSourceFRSettings",
    "KaosSourceGovInfoSettings",
    "KaosSourceHttpSettings",
]
