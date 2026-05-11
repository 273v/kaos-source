# Changelog

All notable changes to `kaos-source` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **Federal Register client preserves multi-value query params.**
  `kaos_source.apis._http.fetch_json` was called with
  `params=dict(list_of_tuples)` from `apis/federal_register/client.py`
  inside `search_documents` and `get_document`. Calling `dict()` on the
  list of `(key, value)` tuples kept only the LAST value per duplicate
  key, so the FR client's `fields[]`, `conditions[agencies][]`, and
  `conditions[type][]` keys all collapsed to a single value. Search
  responses came back with only `json_url` per result; agents that
  called `kaos-source-fr-search` saw "Found N documents" but no
  document_number / title / publication_date / abstract / citation.
  Affected callers had to round-trip every result through
  `get_document()`, burning ~15× the tokens and ~14× the cost. Pass
  the `list[tuple]` through to httpx (which natively accepts both
  forms) and broaden the type hints on `fetch_json` / `fetch_text` to
  match.
- **Roots policy: Windows `file:///C:/...` URIs were rejected.**
  ``_root_path`` parsed root URIs via ``urlparse`` then wrapped
  ``parsed.path`` in ``Path(...)``. On Windows that path comes back
  as ``/C:/Users/...``, which ``Path`` interprets as a drive-relative
  ``\C:\Users\...`` and never matches the resolved target.
  Result: every Windows-x64 CI run that exercised the roots policy
  fell into the deny branch (``SourcePolicyError: Source access
  denied by roots policy``). Switched to ``Path.from_uri`` (Python
  3.13+) on Windows, kept the explicit ``urlparse + unquote`` path on
  POSIX. Regression coverage:
  ``tests/unit/test_hardening.py::TestRootsPolicy.test_root_path_resolves_local_file_uri``
  + ``test_root_path_round_trip_via_assert``.
- **CI: Python 3.15 source-build chain for ``lxml`` + ``pillow``.**
  No published lxml or pillow wheel exists for 3.15 (pre-release)
  yet, so uv falls back to source-build. Added the standard
  apt-get list (``libxml2-dev libxslt-dev libjpeg-dev zlib1g-dev
  libtiff-dev libfreetype6-dev liblcms2-dev libwebp-dev
  libopenjp2-7-dev libimagequant-dev``) gated on
  ``runner.os == 'Linux'``, mirroring the kaos-content +
  kaos-ml-core workflows. Also added ``shell: bash`` on the Install
  dependencies step (it already existed on Run tests).
### Security

- **vulture (dead-code scan) now runs in pre-commit + CI alongside
  the existing bandit job.** New `vulture` hook in
  ``.pre-commit-config.yaml`` mirrored by a new ``vulture (dead-code
  scan)`` job in ``security.yml``. `--min-confidence 100` with the
  shared `--ignore-names` list for names vulture can't infer from
  the import graph (framework callbacks, OAuth/OIDC field names,
  signal handlers, MCP `_meta` keys). Also lands the existing
  bandit hook in pre-commit (it was only in CI before). Both pass
  clean. Mirrors the rollout from kaos-core.

## [0.1.0a2] — 2026-05-08

CI supply-chain hardening (audit-02 F7) and SECURITY.md scope rewrite
(audit-02 F8). Two MD5 call sites tagged `usedforsecurity=False` to
document that they exist for eDiscovery tool compat, not as a security
claim. No public API changes.

### Security

- **F7: CI supply-chain hardening.** `.github/workflows/security.yml`
  pins the gitleaks Docker image to `v8.21.2` (no longer tracking
  `:latest`), adds a Bandit static-analysis job (medium severity /
  medium confidence; `B101,B404,B603,B607` skipped — pytest assertions,
  subprocess use, and known-safe partial-path invocations are
  intentional), and runs the integration suite on `schedule` and
  `workflow_dispatch` so cross-package regressions surface against
  `main` even though the unit gate stays the PR fast path.
- **MD5 calls now opt out of the security claim.**
  `kaos_source.parsers.email.eml._build_attachments` and
  `kaos_source.parsers.metadata.file.parse_file_metadata` both compute
  MD5 alongside SHA-256 / BLAKE2b for eDiscovery tool compatibility —
  not for integrity. They now pass `usedforsecurity=False` to
  `hashlib.md5(...)` so the intent is explicit at the call site and
  Bandit's `B324` warning stays silent under the new gate.

### Changed

- **F8: `SECURITY.md` scope rewritten.** The previous file was a
  two-line placeholder that listed only the package and repo as
  in-scope. The new file describes the actual surface — connector
  transports (filesystem / archive / http / browser / memory), API
  clients (federal_register / ecfr / edgar / govinfo / gleif), parsers
  (eml / mbox / vcard / pacer / file_meta / image_meta), the
  `register_*_tools` MCP tool registrations, and the integrity-bearing
  checksum policy. Out-of-scope correctly lists the upstream API
  operators, third-party dependencies, browser-driver
  vulnerabilities, and configuration-disabled safety features.

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
