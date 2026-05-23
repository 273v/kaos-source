# Changelog

All notable changes to `kaos-source` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [Unreleased]


## [0.1.1] — 2026-05-23

### Added — `[mcp]` extra declared

Declared `[mcp] = ["kaos-mcp>=0.1.0,<0.2"]`. The `kaos-source-serve`
console script, the README MCP-launcher section, and
`kaos_source/serve.py`'s error message all advertised
`pip install 'kaos-source[mcp]'`, but the extra itself was not
declared because `kaos-mcp` was not on PyPI when v0.1.0a1 shipped.
`tests/unit/test_serve_install_contract.py` pins the failure path:
`kaos-source-serve` exits 1 with `[mcp]` and `kaos-source[mcp]` in
stderr when `kaos-mcp` is unavailable. Closes
audit-04/kaos-source.md F-001.

### Changed

- `pyproject.toml` classifier bumped from `Development Status :: 3 - Alpha`
  to `Development Status :: 5 - Production/Stable` to reflect the
  0.1.0 GA release (WU-L #543) that froze the public API for the
  0.1.x line. Closes audit-04/kaos-source.md Family D (classifier drift).

### Changed — `parsers.metadata.file._detect_mime_from_magic` prefers canonical detector

`_detect_mime_from_magic` (called from `extract_file_metadata` when
extension-based MIME guess fails) now prefers
`kaos_nlp_core.content_type.detect()` (0.1.1+) over the in-module
`_MAGIC_SIGNATURES` table. The canonical detector adds an OPC + OLE
fallback that correctly disambiguates real DOCX / PPTX / XLSX / DOC /
XLS / PPT bytes — coverage the in-module table cannot match (it
maps OPC zips to the generic `application/zip` and OLE compound files
to a generic `application/x-ole-storage`).

The in-module table remains as a fallback when kaos-nlp-core isn't
importable at runtime (degraded install) or when the canonical
detector returns `unknown` for bytes the table happens to recognize
— strictly additive; no regression for the formats the legacy table
already handled.

Tracked in `kaos-modules/docs/audits/2026-05-22-content-type-detection-unused.md`
Fix 3.


## [0.1.0] — 2026-05-20

### Changed — WU-L of 0.1.0 GA plan

- 0.1.0 GA — WU-L of the 0.1.0 GA plan. First stable release of
  `kaos-source`. The public API is frozen for the 0.1.x line: no
  breaking changes will land until 0.2.0. Runtime `kaos-core` and
  `[content]` extra / dev-group `kaos-nlp-core` pins raised from
  `>=0.1.0rc1,<0.2` to `>=0.1.0,<0.2`. `kaos-content[html]` floor
  stays at `>=0.1.0a2` (already permissive enough to pick up the
  0.1.0 GA release). No source changes vs 0.1.0rc1.


## [0.1.0rc1] — 2026-05-20

### Changed

- Pin floor raised to `>=0.1.0rc1,<0.2` across kaos-* dependencies
  (`kaos-core` runtime; `kaos-nlp-core` in the `[content]` extra and
  the `dev` group). Refreshed `uv.lock` to pick up `kaos-core
  0.1.0rc1` and `kaos-nlp-core 0.1.0rc1`.

### Internal

- WU-J of the 0.1.0 GA plan
  (`kaos-modules/docs/plans/2026-05-20-0.1.0-ga-plan.md`).
  Release candidate; freezes the public API for `kaos-source`
  ahead of 0.1.0 GA.

## [0.1.0a10] — 2026-05-20

### Added

- **#444 anti-bot fetch + Playwright fallback + per-domain overrides.**
  `kaos-source-fetch-url` now ships a realistic desktop Chrome
  `User-Agent` (and browser-shaped `Accept` / `Accept-Language` /
  `Sec-Fetch-*` headers) by default so hosts that block obvious bot
  UAs (Reuters, Bloomberg, many newsrooms) still serve content on the
  httpx path. When httpx hits an explicit refusal status (`403` /
  `451`) or returns an HTML body matching a known anti-bot
  interstitial fingerprint (Cloudflare "Just a moment...",
  reCAPTCHA / hCaptcha challenge markup, DataDome, PerimeterX,
  Akamai BM "Access Denied"), the tool falls back to a
  `BrowserConnector`-driven Playwright fetch and reports
  `fetch_path: "playwright"` in `structured_content`.

  Playwright stays a soft dependency — install with
  `pip install 'kaos-source[browser]'`. When the extra isn't
  installed and the fallback would fire, the tool returns a
  `ToolResult.create_error(...)` that names the install command and
  the `playwright install chromium` follow-up.

  New typed setting `KaosSourceHttpSettings.domain_overrides:
  dict[str, dict[str, str]]` lets operators set per-domain header
  overrides keyed by host suffix (e.g. `{"reuters.com": {"User-Agent":
  "..."}}`). Longest-suffix match wins. Configurable via
  `KAOS_SOURCE_HTTP_DOMAIN_OVERRIDES` (JSON) or context config.
  Companion `enable_browser_fallback` (default `True`) lets operators
  hard-disable the fallback in restricted environments.

  New structured error `SourceAntiBotChallengeError` (re-exported at
  the package root) carries `locator`, `http_status`, and
  `fingerprint` in `details` so callers can audit triggers.

### Changed

- HTTP connector default `User-Agent` changed from `"kaos-source/0.1"`
  to a realistic Chrome UA. Override via
  `KaosSourceHttpSettings.user_agent`, `KAOS_SOURCE_HTTP_USER_AGENT`,
  or `context.set_config("source_http_user_agent", ...)`.

## [0.1.0a9] — 2026-05-17

### Changed

- **kaos-core floor raised to `>=0.1.0a10`** to pick up the URI
  contract redesign. Pass-through for kaos-source file-input tools.
  See `kaos-modules/docs/plans/uri-contract-redesign.md`.

## [0.1.0a8] — 2026-05-17

### Changed

- **Every file-input MCP tool now routes through
  `kaos_core.path_resolver.resolve_input_path`** via the new
  `kaos_source._path_resolver.resolve_source_input` adapter. Tools
  previously called `Path(p).expanduser().resolve()` + `.exists()` on
  agent input, which could not see files uploaded into the session
  VFS (`KaosRuntime.vfs`) by a UI host such as the kaos-ui
  single-user-chat SPA — the agent then either saw an unbroken
  sequence of `File not found` errors or, worse, hallucinated answers
  from zero successful reads. Each tool's `path` ParameterSchema
  description now explicitly documents the supported shapes
  (absolute filesystem path, `kaos://artifacts/<id>` URI for a
  previously materialised artifact, or a relative path / `kaos://`
  URI that resolves inside the session VFS).

  Tools refactored (9): `kaos-source-discover`, `kaos-source-describe`,
  `kaos-source-preview`, `kaos-source-materialize`,
  `kaos-source-inspect-archive` (runtime), and
  `kaos-source-parse-eml`, `kaos-source-parse-mbox`,
  `kaos-source-email-forensics`, `kaos-source-vcard-parse`,
  `kaos-source-image-metadata`, `kaos-source-file-metadata`,
  `kaos-source-pacer-parse`, `kaos-source-pacer-filter-entries`
  (parsers). On resolver failure the tools return a
  `ToolResult.create_error(...)` whose body is the resolver's
  three-part agent-friendly message (what went wrong + how to fix +
  alternative tool) instead of bare `FileNotFoundError` text.

  `kaos-source-materialize` additionally short-circuits when the
  input was already a `kaos://artifacts/<id>` URI: the existing
  manifest is returned with `already_materialized: true` in
  `structured_content` instead of double-materialising into a
  duplicate artifact. The success path's existing
  `manifest.to_tool_result(...)` emission is preserved unchanged.

  This is Stage 4 of the cross-package
  `vfs-blind-tools-audit-and-fix-plan` in the kaos-modules monorepo
  (`kaos-modules/docs/plans/vfs-blind-tools-audit-and-fix-plan.md`).

### Fixed

- **SES2 — `kaos-source-fetch-url` now refuses `kaos://` URIs with
  agent-friendly guidance** (closes filed task #402). Previously the
  tool routed `kaos://artifacts/<id>` straight into
  `SourceLocator.http(...)` which rejected the scheme with a bare
  `"must use http or https"` message — the agent had no way to know
  the right tool was `kaos-source-materialize` (for a VFS file) or
  `kaos-content-*` (for an already-materialised artifact). A new
  scheme-detection block at the top of `FetchURLTool.execute()`
  short-circuits any URL that starts with `kaos://` and returns a
  clear "this is an internal URI, use these tools instead" error.
  HTTP and HTTPS URLs flow through unchanged.

### Dependencies

- `kaos-core>=0.1.0a9` (bumped from `>=0.1.0a8`) — required for
  `kaos_core.path_resolver.resolve_input_path`, which introduces
  the unified VFS-aware path resolution helper.

## [0.1.0a7] — 2026-05-17

### Changed (hard break — alpha train)

- **`kaos-source-fr-get-content`** (Federal Register) and
  **`kaos-source-ecfr-content`** (eCFR) now materialise fetched content
  as artifacts via `ArtifactStore.create_from_bytes` and return
  `manifest.to_tool_result(...)`. The legacy `max_chars=50_000`
  truncation block is **deleted** — full bodies, no matter the size,
  are addressable via `structured_content.artifact_id`. The artifact
  tier system (`KaosCoreArtifactSettings`, env-overridable via
  `KAOS_CORE_ARTIFACT_INLINE_THRESHOLD` / `_SUMMARY_THRESHOLD`) picks
  inline / summary+link / link-only automatically. `source_uri` is
  populated on the manifest (FR's `doc.html_url`; reconstructed eCFR
  versioner URL).

  **Structured-content schema change** (intentional break, per the
  alpha train's "explicitly unstable" status): the old `content`,
  `truncated`, and `length` keys are gone. New keys: `artifact_id`,
  `body_uri`, `size`, `mime_type` (plus the original
  `document_number` / `title` / `format` / `source_url` for FR, and
  `title` / `section` / `part` / `date` / `format` for eCFR).
  Downstream callers migrate by reading
  `structured_content.artifact_id` and calling `store.read_text(id)`
  when they need the body.

- Both tools now require a `KaosRuntime` via the `KaosContext`
  parameter (mirror of `FetchURLTool`'s pattern at
  `runtime/tools.py:450-527`). Callers without runtime context get a
  clear error pointing at that requirement.

### Why

This is Stage B2 of the cross-package
`no-hardcoded-caps-and-artifact-first-tool-results` plan in the
kaos-modules monorepo. The 50_000 char cap on FR / eCFR content has
been a chronic correctness bug — long regulations like Reg S-P
(~107 KB) were silently truncated, leaving downstream agents
hallucinating from incomplete inputs. The artifact path materialises
the full body once, exposes it via the resource link, and lets
consumers (agents, the SPA Documents panel, kaos-content downstream
tools) read all of it.

### Dependencies

- `kaos-core>=0.1.0a8` (bumped from `>=0.1.0a4`) — required for
  `ArtifactStore.create_from_bytes`, `ArtifactManifest.source_uri`, and
  the `KaosCoreArtifactSettings`-driven `to_tool_result` tier
  selection.

## [0.1.0a6] — 2026-05-15

### Added — `tags=["forensics"]` on offline tools (PRD PR 2 Stage A.5)

Every offline kaos-source tool now carries `tags=["forensics"]` so
kaos-agents' `derive_group()` (introduced in kaos-agents 0.1.0a3)
classifies them into the SessionToolSet `forensics` group rather than
the broader `documents` group.

Affected tools (13 total):

- **Core discovery** (5): `kaos-source-discover`, `kaos-source-describe`,
  `kaos-source-preview`, `kaos-source-materialize`,
  `kaos-source-inspect-archive`
- **PACER** (2): `kaos-source-pacer-parse`,
  `kaos-source-pacer-filter-entries`
- **vCard** (1): `kaos-source-vcard-parse`
- **Email** (3): `kaos-source-parse-eml`, `kaos-source-parse-mbox`,
  `kaos-source-email-forensics`
- **Metadata** (2): `kaos-source-file-metadata`,
  `kaos-source-image-metadata`

`kaos-source-fetch-url` deliberately does NOT carry the tag — it
performs network egress (`openWorldHint=True`) and belongs in the
`web` group via the kaos-agents derivation, not `forensics`.

Tests:
  - 2 new tests in `tests/unit/test_tools.py` pinning the tag coverage:
    every forensics tool carries the tag, and `fetch-url` does not.

Motivated by `kaos-modules/docs/internal/dynamic-tool-planning-completion-plan.md`
§4 Stage A.5. Purely additive: the `tags` field was empty before;
classification works unchanged for callers that don't read tags.

## [0.1.0a5] — 2026-05-15

### Added — web + forensics registration entry points (PRD PR 1)

- **`register_source_web_tools(runtime)`** — registers the 17
  online (network-accessing) source tools: `kaos-source-fetch-url`
  plus every Federal Register / eCFR / GovInfo / SEC EDGAR / GLEIF
  API tool. Pins the SessionToolSet `web` group entry point: a
  session that grants network egress sees exactly these tools.
- **`register_source_forensics_tools(runtime)`** — registers the
  13 offline (local byte-processing) source tools: filesystem
  discovery (`discover`, `describe`, `preview`, `materialize`,
  `inspect-archive`), PACER docket parser (2 tools), vCard parser,
  email parser bundle (`parse-eml`, `parse-mbox`,
  `email-forensics`), and file / image metadata extractors. Pins
  the SessionToolSet `forensics` group entry point. Default-on
  at the ceiling because every tool is read-only on bytes the
  session already controls — no network egress.
- **`register_source_tools(runtime)`** is now a backward-compatible
  union of the two — every existing caller continues to see the
  same 30 tools with the same names and schemas.

Motivated by `kaos-modules/docs/internal/dynamic-tool-planning-prd.md`
§4 ("PR 1 — catalog expansion"; round-2 decision #5). Purely
additive: no tool name, schema, or behavior changes.

## [0.1.0a4] — 2026-05-15

### Fixed

- **`kaos-source-fs-list` and `kaos-source-archive-list` `patterns`
  parameters now declare their element type.** Both were
  previously `type=array` with no `items`, which OpenAI's strict
  JSON Schema validator rejected with HTTP 400
  `invalid_function_parameters`, taking down the whole tool catalog
  for the turn. Now `items: {type: "string"}` because the patterns
  are glob strings. kaos-core 0.1.0a7's defensive `items: {}` floor
  is belt + suspenders.

- **CI: nightly integration tests now allow loopback for local
  fixtures.** kaos-core 0.1.0a5's strict-by-default SSRF guard
  (``KaosSecuritySettings.block_loopback=True``) rejected the tests'
  own ``127.0.0.1`` test server with ``SourcePolicyError``,
  cascading to ``httpx.ConnectError`` + ``BrokenPipeError`` on the
  MCP-over-stdio legs. Set ``KAOS_SECURITY_BLOCK_LOOPBACK=false`` on
  the scheduled-only ``integration`` job in ``security.yml`` so the
  local fixture HTTP server is reachable. Push/PR runs of
  ``security.yml`` are unchanged (the job has ``if: github.event_name
  == 'schedule' || github.event_name == 'workflow_dispatch'``). No
  runtime behavior change.


## [0.1.0a3] — 2026-05-11

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
### Changed

- **uv.lock is now tracked in git.** Previously gitignored at v0.1.0a1
  because the ``[mcp]`` optional extra (and the ``kaos-mcp`` dev
  dependency) referenced a sibling not yet on PyPI; ``uv lock``
  couldn't resolve them. ``kaos-mcp`` shipped (0.1.0a2), so the
  original gating reason no longer applies. Tracking the lockfile
  gives reproducible local dev environments, lets Dependabot surface
  sibling-version bumps as PRs, and makes the supply-chain pin set
  publicly auditable. Mirrors the org-wide convention being adopted
  across all 16 kaos-* repos.

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

[Unreleased]: https://github.com/273v/kaos-source/compare/v0.1.0a3...HEAD
[0.1.0a3]: https://github.com/273v/kaos-source/compare/v0.1.0a2...v0.1.0a3
[0.1.0a1]: https://github.com/273v/kaos-source/releases/tag/v0.1.0a1
