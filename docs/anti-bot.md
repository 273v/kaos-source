# Anti-bot fetch hardening

Tracking: [issue #444](https://github.com/273v/kaos-source/issues/444),
shipped in `kaos-source 0.1.0a10`.

This page documents how `kaos-source-fetch-url` resists three common
classes of "we don't serve bots" refusal:

1. Hosts that gate on an obvious bot `User-Agent` string.
2. Hosts that return `HTTP 403` or `HTTP 451` to unknown UAs even
   when the request is otherwise legitimate.
3. Hosts that serve a JavaScript-rendered interstitial (Cloudflare,
   hCaptcha / reCAPTCHA, DataDome, PerimeterX, Akamai BM) before the
   real content.

The default behavior on the httpx path stays honest — we don't rotate
UAs or pretend to be a different browser per request. The defaults are
just shaped so the wire-level shape of an outbound request matches
what a real desktop Chrome would send.

## Realistic UA default

`KaosSourceHttpSettings.user_agent` now defaults to a current desktop
Chrome string, defined once in
[`kaos_source/settings/http.py`](../kaos_source/settings/http.py) as
`DEFAULT_HTTP_UA`:

```python
DEFAULT_HTTP_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
```

Paired with this UA, the HTTP connector also sends `Accept`,
`Accept-Language`, and the `Sec-Fetch-*` family by default
(`DEFAULT_BROWSER_HEADERS`). Hosts that gate on header *presence*
rather than UA value also pass.

Override sources (later wins):

1. `DEFAULT_BROWSER_HEADERS` (built-in).
2. Connector-constructor `default_headers`.
3. `KaosSourceHttpSettings.headers` global headers.
4. `KaosSourceHttpSettings.user_agent` (User-Agent only).
5. `KaosSourceHttpSettings.domain_overrides` (most specific).

## Per-domain header overrides

`KaosSourceHttpSettings.domain_overrides: dict[str, dict[str, str]]`
sets headers per host. Keys are host suffixes — `"reuters.com"` matches
`www.reuters.com` and `feeds.reuters.com` alike. Longest matching key
wins.

Via environment variable (JSON):

```bash
export KAOS_SOURCE_HTTP_DOMAIN_OVERRIDES='{
  "reuters.com": {
    "User-Agent": "ResearchBot research@example.com",
    "Accept": "text/html"
  },
  "sec.gov": {
    "User-Agent": "Example Research Co research@example.com"
  }
}'
```

Via `KaosContext` config (preferred when you want per-session
overrides):

```python
context.set_config(
    "source_http_domain_overrides",
    {"reuters.com": {"User-Agent": "ResearchBot research@example.com"}},
)
```

Via direct `KaosSourceHttpSettings` construction:

```python
from kaos_source.settings import KaosSourceHttpSettings

settings = KaosSourceHttpSettings(
    domain_overrides={
        "sec.gov": {"User-Agent": "Example Research research@example.com"},
    }
)
```

## When the Playwright fallback fires

The HTTP connector raises a structured `SourceAntiBotChallengeError`
when *any* of the following happen on the materialize path:

1. The response status is **403** or **451** (anti-bot refusal or
   geofence).
2. The response is HTML-typed and the first ~16 KB of the body
   contains one of the known fingerprint substrings:

   | Label                       | Substring matched (case-insensitive)        |
   | --------------------------- | ------------------------------------------- |
   | `cloudflare_just_a_moment`  | `<title>just a moment...`                   |
   | `cloudflare_challenge`      | `checking your browser before accessing`    |
   | `cloudflare_attention`      | `attention required! \| cloudflare`         |
   | `cloudflare_ray`            | `cloudflare ray id:`                        |
   | `cf_chl`                    | `cf-chl-bypass`                             |
   | `hcaptcha`                  | `hcaptcha-challenge`                        |
   | `recaptcha_solve`           | `please solve the captcha`                  |
   | `recaptcha_challenge`       | `class="g-recaptcha"`                       |
   | `perimeterx`                | `px-captcha`                                |
   | `datadome`                  | `datadome-captcha`                          |
   | `akamai_bm`                 | `<title>access denied</title>`              |
   | `generic_captcha_title`     | `<title>captcha</title>`                    |

   The full list lives in
   [`kaos_source/connectors/http.py`](../kaos_source/connectors/http.py)
   as `_ANTI_BOT_FINGERPRINTS`. Non-HTML responses skip the body
   sniff entirely.

The `FetchURLTool` catches `SourceAntiBotChallengeError` and, if
`KaosSourceHttpSettings.enable_browser_fallback` is `True` (default),
re-runs `materialize` against the same URL through a one-shot
`BrowserConnector`-backed service. The resulting `ToolResult` carries:

```json
{
  "fetch_path": "playwright",
  "fallback_reason": "cloudflare_just_a_moment"
}
```

so callers can distinguish a normal httpx fetch from a fallback fetch.

To hard-disable the fallback (e.g. in environments where outbound
Playwright traffic isn't permitted):

```bash
export KAOS_SOURCE_HTTP_ENABLE_BROWSER_FALLBACK=0
```

## Installing the `[browser]` extra

Playwright is an **optional dependency**. Install it explicitly:

```bash
pip install 'kaos-source[browser]'
python -m playwright install chromium
```

If the fallback fires and the import fails, `FetchURLTool` returns a
`ToolResult.create_error(...)` whose `error_text` looks like:

> Fetch failed for 'https://example.com/blocked': blocked by anti-bot
> challenge (fingerprint='http_403'). Playwright is required to bypass
> this kind of refusal, but the [browser] extra is not installed.
>
>     pip install 'kaos-source[browser]'
>     python -m playwright install chromium
>
> Then retry the same kaos-source-fetch-url call. The host can still
> legitimately refuse Playwright; if so, the next error will state
> that explicitly.

If Playwright is installed but the host *also* refuses the browser
fetch (some bot-walls do), the tool surfaces the underlying
`BrowserConnector` error verbatim so the operator can act on it.

## Limitations

- The fingerprint list is conservative on purpose; false positives on
  benign content can blackhole legitimate pages into the Playwright
  path. If you see a false-positive trigger, add a test case and PR
  a tightened needle.
- The fallback creates a fresh Playwright context per call. For
  high-volume browser fetches use `BrowserConnector` directly through
  `kaos-web` tools so you get the connection-reuse and screenshot
  options.
- The fallback does not currently respect per-domain header overrides
  (Playwright manages its own UA via `KaosSourceBrowserSettings`).
- Body-sniffing only inspects the first 16 KB. Pathological
  challenge pages that bury their fingerprint past that window slip
  through.
