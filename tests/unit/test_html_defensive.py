"""Defensive integration tests for the kaos-content seam.

kaos-source consumes ``kaos-content[html]`` for HTML→AST conversion
in the EDGAR pipeline (and anywhere else that constructs a
``ContentDocument`` from HTML). Two security findings in the
2026-05-07 review affect us as a consumer:

- **Sec-1 / finding #3**: ``urlparse`` raised ``ValueError`` on
  malformed URLs like ``http://[`` (bare IPv6 open bracket). An
  agent fetching a page with a malformed ``<a href>`` would crash
  the EDGAR client.
- **Sec-4 / finding #4**: dangerous-URL handler dropped the link's
  inner text — ``<a href="javascript:...">click me</a>`` collapsed
  to nothing. Visible content was silently lost from filings.

Both are fixed in kaos-content. These tests defend kaos-source
specifically against re-regression: even if a future kaos-content
change re-breaks either property, we'd see it here at the
consumer-test layer.
"""

from __future__ import annotations

import pytest

# Skip if kaos-content[html] isn't installed in this environment.
parse_html = pytest.importorskip("kaos_content.parsers.html").parse_html
serialize_text = pytest.importorskip("kaos_content.serializers.text").serialize_text


# ----- Sec-1 / #3: malformed URL must not crash --------------------------


@pytest.mark.parametrize(
    "html",
    [
        # Bare IPv6 open bracket — the original PoC.
        '<p>before <a href="http://[">click</a> after</p>',
        # Inside <img src>.
        '<p><img src="http://[" alt="x" /></p>',
        # Inside other URL-bearing attributes that EDGAR filings might use.
        '<p><a href="https://[::1">click</a></p>',
    ],
)
def test_malformed_url_does_not_crash_parser(html: str) -> None:
    # Must not raise. The EDGAR pipeline ingests filings that contain
    # arbitrary HTML; a malformed href in any one filing must not
    # propagate as an exception to the agent.
    doc = parse_html(html)
    assert doc is not None


# ----- Sec-4 / #4: dangerous-link text preservation ----------------------


@pytest.mark.parametrize(
    "scheme",
    [
        "javascript:void(0)",
        "javascript:alert(1)",
        "vbscript:msgbox(1)",
        "data:text/html,<script>alert(1)</script>",
        "file:///etc/passwd",
    ],
)
def test_dangerous_link_inner_text_preserved(scheme: str) -> None:
    """For any unsafe URL scheme, the visible link text survives.

    EDGAR filings are user-authored HTML; an analyst reading text
    extracted by kaos-source must see every glyph the source page
    showed, even if the underlying link was dropped for being
    dangerous. Pre-fix the inner text was silently swallowed.
    """
    html = f'<p>before <a href="{scheme}">click me</a> after</p>'
    doc = parse_html(html)
    text = serialize_text(doc).strip()
    assert "before" in text, f"'before' lost (scheme={scheme!r}): {text!r}"
    assert "click me" in text, f"Inner link text was dropped (scheme={scheme!r}): {text!r}"
    assert "after" in text, f"'after' lost (scheme={scheme!r}): {text!r}"


def test_safe_link_unchanged() -> None:
    """Sanity: regular links round-trip with their text intact."""
    html = '<p>before <a href="https://example.com">click me</a> after</p>'
    doc = parse_html(html)
    text = serialize_text(doc).strip()
    assert "click me" in text
