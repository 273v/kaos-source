"""Tests for kaos_source.settings — typed HTTP and browser settings."""

from __future__ import annotations

from typing import Any

import pytest

from kaos_source.settings import KaosSourceBrowserSettings, KaosSourceHttpSettings
from kaos_source.settings.http import DEFAULT_BROWSER_HEADERS, DEFAULT_HTTP_UA


class _FakeContext:
    """Minimal stand-in for KaosContext with _config dict."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config: dict[str, Any] = config or {}


# ---------------------------------------------------------------------------
# KaosSourceHttpSettings
# ---------------------------------------------------------------------------


class TestHttpSettingsDefaults:
    def test_defaults(self) -> None:
        s = KaosSourceHttpSettings()
        assert s.timeout_seconds == 30.0
        assert s.retry_limit == 2
        assert s.allowed_hosts is None
        assert s.max_concurrent_per_domain == 2
        assert s.min_interval_seconds == 0.0
        assert s.headers is None
        # Issue #444 — realistic Chrome UA by default so hosts that
        # block obvious bot UAs still serve the page.
        assert s.user_agent == DEFAULT_HTTP_UA
        assert "Chrome/" in s.user_agent
        assert "Mozilla/5.0" in s.user_agent
        assert s.verify_ssl is True
        assert s.follow_redirects is True
        assert s.http2 is False
        # Per-domain overrides default empty; browser fallback opt-in by default.
        assert s.domain_overrides is None
        assert s.enable_browser_fallback is True


class TestHttpSettingsAntiBotDefaults:
    """Issue #444 — defaults for the anti-bot fetch hardening."""

    def test_default_browser_headers_present(self) -> None:
        # These are the headers the connector layers under any
        # user-provided override; surface the constant so callers
        # can introspect what gets sent.
        assert "Accept" in DEFAULT_BROWSER_HEADERS
        assert "Accept-Language" in DEFAULT_BROWSER_HEADERS
        assert DEFAULT_BROWSER_HEADERS["Sec-Fetch-Mode"] == "navigate"

    def test_domain_overrides_round_trip(self) -> None:
        s = KaosSourceHttpSettings(
            domain_overrides={
                "reuters.com": {"User-Agent": "Custom/1.0", "Accept": "text/html"},
            }
        )
        assert s.domain_overrides is not None
        assert s.domain_overrides["reuters.com"]["User-Agent"] == "Custom/1.0"

    def test_browser_fallback_env_toggle(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KAOS_SOURCE_HTTP_ENABLE_BROWSER_FALLBACK", "0")
        s = KaosSourceHttpSettings()
        assert s.enable_browser_fallback is False


class TestRetryBackoffSettings:
    def test_defaults(self) -> None:
        s = KaosSourceHttpSettings()
        assert s.retry_initial_delay == 0.1
        assert s.retry_max_delay == 1.0

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KAOS_SOURCE_HTTP_RETRY_INITIAL_DELAY", "0.5")
        monkeypatch.setenv("KAOS_SOURCE_HTTP_RETRY_MAX_DELAY", "5.0")
        s = KaosSourceHttpSettings()
        assert s.retry_initial_delay == 0.5
        assert s.retry_max_delay == 5.0

    def test_legacy_context_fallback(self) -> None:
        """Legacy prefixed keys in context should work."""
        ctx = _FakeContext(
            {"source_http_retry_initial_delay": 0.2, "source_http_retry_max_delay": 2.0}
        )
        s = KaosSourceHttpSettings.from_context(ctx)
        assert s.retry_initial_delay == 0.2
        assert s.retry_max_delay == 2.0


class TestHttpSettingsEnvVars:
    def test_env_vars_with_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KAOS_SOURCE_HTTP_TIMEOUT_SECONDS", "60.0")
        monkeypatch.setenv("KAOS_SOURCE_HTTP_RETRY_LIMIT", "5")
        monkeypatch.setenv("KAOS_SOURCE_HTTP_USER_AGENT", "test-agent/2.0")
        monkeypatch.setenv("KAOS_SOURCE_HTTP_VERIFY_SSL", "false")
        monkeypatch.setenv("KAOS_SOURCE_HTTP_HTTP2", "true")

        s = KaosSourceHttpSettings()
        assert s.timeout_seconds == 60.0
        assert s.retry_limit == 5
        assert s.user_agent == "test-agent/2.0"
        assert s.verify_ssl is False
        assert s.http2 is True


class TestHttpSettingsFromContext:
    def test_new_style_field_names(self) -> None:
        ctx = _FakeContext({"timeout_seconds": 45.0, "retry_limit": 3})
        s = KaosSourceHttpSettings.from_context(ctx)
        assert s.timeout_seconds == 45.0
        assert s.retry_limit == 3

    def test_legacy_source_http_prefix(self) -> None:
        ctx = _FakeContext({"source_http_timeout_seconds": 60.0, "source_http_retry_limit": 4})
        s = KaosSourceHttpSettings.from_context(ctx)
        assert s.timeout_seconds == 60.0
        assert s.retry_limit == 4

    def test_bare_fallback_keys(self) -> None:
        ctx = _FakeContext({"timeout": 90.0, "retry_limit": 7})
        s = KaosSourceHttpSettings.from_context(ctx)
        assert s.timeout_seconds == 90.0
        assert s.retry_limit == 7

    def test_new_style_takes_precedence_over_legacy(self) -> None:
        ctx = _FakeContext(
            {
                "timeout_seconds": 10.0,
                "source_http_timeout_seconds": 20.0,
                "timeout": 30.0,
            }
        )
        s = KaosSourceHttpSettings.from_context(ctx)
        assert s.timeout_seconds == 10.0

    def test_legacy_takes_precedence_over_bare(self) -> None:
        ctx = _FakeContext(
            {
                "source_http_timeout_seconds": 20.0,
                "timeout": 30.0,
            }
        )
        s = KaosSourceHttpSettings.from_context(ctx)
        assert s.timeout_seconds == 20.0

    def test_explicit_overrides_win(self) -> None:
        ctx = _FakeContext({"timeout_seconds": 10.0})
        s = KaosSourceHttpSettings.from_context(ctx, timeout_seconds=99.0)
        assert s.timeout_seconds == 99.0

    def test_allowed_hosts_via_legacy_key(self) -> None:
        ctx = _FakeContext({"source_http_allowed_hosts": ["*.example.com"]})
        s = KaosSourceHttpSettings.from_context(ctx)
        assert s.allowed_hosts == ["*.example.com"]

    def test_headers_via_legacy_key(self) -> None:
        ctx = _FakeContext({"source_http_headers": {"Accept-Language": "en-US"}})
        s = KaosSourceHttpSettings.from_context(ctx)
        assert s.headers == {"Accept-Language": "en-US"}

    def test_user_agent_via_legacy_key(self) -> None:
        ctx = _FakeContext({"source_http_user_agent": "KAOS-Test-Agent/1.0"})
        s = KaosSourceHttpSettings.from_context(ctx)
        assert s.user_agent == "KAOS-Test-Agent/1.0"

    def test_no_context_returns_defaults(self) -> None:
        s = KaosSourceHttpSettings.from_context(None)
        assert s.timeout_seconds == 30.0
        assert s.retry_limit == 2

    def test_empty_context_returns_defaults(self) -> None:
        ctx = _FakeContext({})
        s = KaosSourceHttpSettings.from_context(ctx)
        assert s.timeout_seconds == 30.0


class TestHttpSettingsPrecedence:
    def test_override_gt_context_gt_env_gt_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KAOS_SOURCE_HTTP_TIMEOUT_SECONDS", "10.0")
        ctx = _FakeContext({"timeout_seconds": 20.0})

        # env alone
        s1 = KaosSourceHttpSettings()
        assert s1.timeout_seconds == 10.0

        # context overrides env
        s2 = KaosSourceHttpSettings.from_context(ctx)
        assert s2.timeout_seconds == 20.0

        # explicit override wins over context
        s3 = KaosSourceHttpSettings.from_context(ctx, timeout_seconds=50.0)
        assert s3.timeout_seconds == 50.0


# ---------------------------------------------------------------------------
# KaosSourceBrowserSettings
# ---------------------------------------------------------------------------


class TestBrowserSettingsDefaults:
    def test_defaults(self) -> None:
        s = KaosSourceBrowserSettings()
        assert s.allowed_hosts is None
        assert s.max_concurrent_per_domain == 1
        assert s.user_agent == "kaos-source-browser/0.1"
        assert s.headers is None
        assert s.headless is True
        assert s.timeout_ms == 30_000
        assert s.wait_until == "networkidle"
        assert s.take_screenshot is True
        assert s.screenshot_full_page is True
        assert s.ignore_https_errors is False


class TestBrowserSettingsEnvVars:
    def test_env_vars_with_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KAOS_SOURCE_BROWSER_HEADLESS", "false")
        monkeypatch.setenv("KAOS_SOURCE_BROWSER_TIMEOUT_MS", "60000")
        monkeypatch.setenv("KAOS_SOURCE_BROWSER_WAIT_UNTIL", "load")
        monkeypatch.setenv("KAOS_SOURCE_BROWSER_TAKE_SCREENSHOT", "false")

        s = KaosSourceBrowserSettings()
        assert s.headless is False
        assert s.timeout_ms == 60_000
        assert s.wait_until == "load"
        assert s.take_screenshot is False


class TestBrowserSettingsFromContext:
    def test_new_style_field_names(self) -> None:
        ctx = _FakeContext({"headless": False, "timeout_ms": 15000})
        s = KaosSourceBrowserSettings.from_context(ctx)
        assert s.headless is False
        assert s.timeout_ms == 15000

    def test_legacy_source_browser_prefix(self) -> None:
        ctx = _FakeContext(
            {
                "source_browser_headless": False,
                "source_browser_timeout_ms": 20000,
                "source_browser_user_agent": "test-browser/1.0",
            }
        )
        s = KaosSourceBrowserSettings.from_context(ctx)
        assert s.headless is False
        assert s.timeout_ms == 20000
        assert s.user_agent == "test-browser/1.0"

    def test_new_style_takes_precedence_over_legacy(self) -> None:
        ctx = _FakeContext(
            {
                "headless": True,
                "source_browser_headless": False,
            }
        )
        s = KaosSourceBrowserSettings.from_context(ctx)
        assert s.headless is True

    def test_explicit_overrides_win(self) -> None:
        ctx = _FakeContext({"timeout_ms": 10000})
        s = KaosSourceBrowserSettings.from_context(ctx, timeout_ms=5000)
        assert s.timeout_ms == 5000

    def test_allowed_hosts_via_legacy_key(self) -> None:
        ctx = _FakeContext({"source_browser_allowed_hosts": ["*.example.com"]})
        s = KaosSourceBrowserSettings.from_context(ctx)
        assert s.allowed_hosts == ["*.example.com"]

    def test_no_context_returns_defaults(self) -> None:
        s = KaosSourceBrowserSettings.from_context(None)
        assert s.headless is True
        assert s.timeout_ms == 30_000


class TestBrowserSettingsPrecedence:
    def test_override_gt_context_gt_env_gt_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KAOS_SOURCE_BROWSER_TIMEOUT_MS", "10000")
        ctx = _FakeContext({"timeout_ms": 20000})

        # env alone
        s1 = KaosSourceBrowserSettings()
        assert s1.timeout_ms == 10000

        # context overrides env
        s2 = KaosSourceBrowserSettings.from_context(ctx)
        assert s2.timeout_ms == 20000

        # explicit override wins over context
        s3 = KaosSourceBrowserSettings.from_context(ctx, timeout_ms=50000)
        assert s3.timeout_ms == 50000
