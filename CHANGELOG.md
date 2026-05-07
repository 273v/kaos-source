# Changelog

All notable changes to `kaos-source` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0a1] — 2026-05-07

First public alpha release.

### Added

- **Source discovery layer** — typed `SourceLocator`, `SourceDescriptor`,
  `SourcePreview`, `SourceMaterialization`, `SourceJob` models plus the
  `SourceConnector` / `ApiConnector` / `SourceParser` ABCs, three
  registries (`ConnectorRegistry` / `ApiRegistry` / `ParserRegistry`),
  and the `SourceService` runtime that routes operations across them.
- **Five transport connectors** — filesystem, archive (ZIP / TAR),
  in-memory, HTTP, and Playwright-backed browser.
- **Five REST API connectors** — Federal Register, eCFR, EDGAR (SEC),
  GovInfo, GLEIF (LEI).
- **Six file-format parsers** — VCard (RFC 6350 / 2426 / 2.1),
  EML / MBOX with full forensic header analysis (Received chain,
  SPF / DKIM / DMARC, threading, attachment hashing), PACER docket
  HTML, image EXIF (Pillow), generic file metadata.
- **30 MCP tools** registered via `register_source_tools` plus per-API
  / per-parser `register_*_tools` helpers.
- **Per-module typed settings** — `KaosSourceHttpSettings`,
  `KaosSourceBrowserSettings`, `KaosSourceFRSettings`,
  `KaosSourceECFRSettings`, `KaosSourceGovInfoSettings`,
  `KaosSourceEdgarSettings` with `KAOS_SOURCE_*` env prefixes and
  legacy fallbacks (`GOVINFO_API_KEY`, `SEC_EDGAR_USER_AGENT`).
- **Typed error hierarchy** — `SourceError` base with
  `SourceAccessError`, `SourceMaterializationError`, `SourceNotFoundError`,
  `SourcePolicyError`, `SourceTransientError`, `SourceValidationError`
  subclasses, all inheriting `KaosCoreError` for unified handling.

### Security

- **KSRC-01 — XXE / entity-expansion guard on the PACER parser.** The
  PACER docket HTML parser previously called `lxml.html.fromstring`
  with the default lxml parser settings, which on libxml2 builds with
  entity resolution enabled would expand DOCTYPE-declared entities.
  Fix: a module-local `HTMLParser(no_network=True, huge_tree=False,
  recover=True, remove_blank_text=False)` is passed explicitly to
  `html.fromstring`. `no_network` blocks SYSTEM-entity fetches;
  `huge_tree=False` keeps the libxml2 input-size and entity-expansion
  caps in place. Mirrors the same fix in `kaos-content` 0.1.0a2
  (KCONT-01). Regression tests in `tests/unit/test_pacer.py`.

- **KSRC-02 — response size caps on every outbound API call.** The
  EDGAR / Federal Register / eCFR / GLEIF clients previously called
  `resp.json()` on untrusted server responses with no `Content-Length`
  pre-check or streamed-read budget. A misbehaving server could
  exhaust the process via a multi-GB JSON payload. Fix: every API
  call now goes through `kaos_source.apis._http.fetch_json` /
  `fetch_text`, which compose `kaos_core.security.read_capped_json`
  (kaos-core 0.1.0a4) with the API-status helper below. Cap is
  configurable via `KAOS_SECURITY_RESPONSE_MAX_BYTES` (default 100 MB).

- **KSRC-03 — archive decompression-bomb caps.** `ArchiveConnector._iter_members`
  now enforces `max_decompression_ratio` (default 100:1, computed from
  ZIP central-directory `compressed_size` / `uncompressed_size`) and
  `max_total_uncompressed` (default 10 GiB cumulative cap across all
  members). Both knobs live on `SourceDiscoverOptions`. Catches the
  classic billion-zero ZIP bomb at iteration time, before any member
  bytes are read.

- **KSRC-04 — SSRF guard on the HTTP connector.** The HTTP connector
  now calls `kaos_core.security.validate_outbound_url` on every
  request, including each redirect hop (via httpx's request event
  hook). Strict-by-default: blocks RFC1918 / ULA / link-local
  destinations, IPv4/IPv6 loopback, and known cloud instance-metadata
  endpoints (AWS / Azure / GCP IMDS). Configurable via
  `KAOS_SECURITY_*` env vars or per-call kwargs; the connector's own
  `allowed_hosts` allowlist is unioned into the SSRF allowlist so
  operators don't have to maintain two lists.

- **KSRC-05 — EDGAR User-Agent format validation.**
  `KaosSourceEdgarSettings.require_user_agent` now rejects empty,
  whitespace-only, and missing-`@` UA strings before any HTTP call,
  with recovery guidance pointing at the SEC EDGAR access page.
  Pre-fix, a misconfigured UA surfaced as a cryptic 403 / 429 from
  the SEC at request time.

- **KSRC-06 — TAR symlink / hardlink members skipped by default.**
  `ArchiveConnector` now skips any TAR member with type `SYMTYPE`
  or `LNKTYPE` unless the caller explicitly passes
  `SourceDiscoverOptions(allow_symlinks=True)`. Blocks the classic
  `../../etc/passwd`-shaped archive-escape attack vector. ZIP cannot
  encode symlinks at the format level; nothing changes there.

- **KSRC-07 — EDGAR `Retry-After` honored.** API clients now go
  through a shared `kaos_source.apis._http.raise_api_status` helper
  that translates `429` / `5xx` responses into
  `SourceTransientError(retry_after_seconds=...)`. Both delta-seconds
  and HTTP-date forms of `Retry-After` are parsed (reusing
  `HttpConnector._retry_after_seconds`), so upstream backoff logic
  can do the right thing.

- **KSRC-08 — SHA-256 alongside MD5 for email attachments.** The EML
  parser now computes both an MD5 (retained for eDiscovery /
  forensic-tool compatibility — Enron NSRL, EnCase, Magnet) and a
  SHA-256 (the authoritative integrity field) for each attachment.
  The `Attachment.sha256` field is the new authoritative integrity
  hash; `Attachment.md5` is documented as legacy.

[Unreleased]: https://github.com/273v/kaos-source/compare/v0.1.0a1...HEAD
[0.1.0a1]: https://github.com/273v/kaos-source/releases/tag/v0.1.0a1
