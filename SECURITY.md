# Security policy

## Reporting a vulnerability

We take security seriously. If you believe you have found a security
vulnerability in `kaos-source`, please report it privately so we can address it
before public disclosure.

**Please do not file a public GitHub issue for security reports.**

### How to report

Use [GitHub Private Vulnerability Reporting](https://github.com/273v/kaos-source/security/advisories/new)
to send a report. Alternatively, email **security@273ventures.com**.

Include as much of the following as you can:

- A description of the vulnerability and its impact
- Steps to reproduce, including affected versions
- Any proof-of-concept code, if available
- Suggested mitigations, if you have any

### What to expect

- **Acknowledgement** — within 3 business days of your report.
- **Initial triage** — within 7 business days, including a severity assessment.
- **Fix and disclosure** — coordinated with you. Our target window is 90 days
  from acknowledgement to public disclosure, faster for high-severity issues.
- **Credit** — we credit reporters in the release notes and security advisory
  unless you prefer to remain anonymous.

## Supported versions

`kaos-source` follows Semantic Versioning. While the project is pre-1.0, only
the latest minor release receives security fixes. After 1.0, the latest two
minor releases will be supported.

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |
| < 0.1   | No        |

## Scope

`kaos-source` provides source discovery, retrieval, and parsing for
KAOS. It exposes:

- **`SourceConnector` transports**: filesystem, archive, http, browser,
  memory.
- **`ApiConnector` REST clients**: federal_register, ecfr, edgar,
  govinfo, gleif. The govinfo client reads `KAOS_SOURCE_GOVINFO_API_KEY`
  or `GOVINFO_API_KEY` from the environment; agent runners (e.g. via
  `kaos-mcp`'s setup helpers) supply the value through env-var
  references rather than persisting the literal secret.
- **`SourceParser` implementations**: vcard, email (`eml`, `mbox`,
  family), pacer, file metadata, image metadata.
- **MCP tool registrations**: `register_ecfr_tools`,
  `register_edgar_tools`, `register_federal_register_tools`,
  `register_gleif_tools`, `register_govinfo_tools`.

In-scope:

- The `kaos-source` Python package as published on PyPI
- The `273v/kaos-source` GitHub repository (CI, release, supply chain)
- Connector input handling — URL allowlists, archive extraction
  (zip-bomb / path-traversal protection), browser navigation safety
- API client hardening — request signing, rate limiting, response
  validation, redaction of API keys from log output
- Parser input handling — malformed eml / mbox / vcard, deeply nested
  MIME trees, oversize attachments, binary-checksum integrity
- Tool boundary (`register_*_tools` outputs) — input validation,
  response shaping, tool annotation correctness
  (`readOnlyHint`, `idempotentHint`)
- File metadata checksums — SHA-256 / BLAKE2b are the integrity-bearing
  digests; MD5 is computed only with `usedforsecurity=False` for
  eDiscovery tool compat
- OIDC trusted-publishing release pipeline

Out of scope:

- Vulnerabilities in third-party dependencies — report upstream
  (`httpx`, `lxml`, `pydantic`, `kaos-core`, `kaos-content`,
  `kaos-nlp-core`).
- Provider-side issues at the upstream API endpoints (Federal Register,
  eCFR, EDGAR, govinfo.gov, GLEIF) — report to the operator of each
  service.
- MCP transport security — that surface lives in `kaos-mcp`; report
  there.
- Browser-driver vulnerabilities (Playwright / Chromium) — report
  upstream.
- Issues caused by user-supplied configuration that explicitly disables
  safety features (e.g. `verify_ssl=False`, lifting connector
  allowlists, bypassing rate limits).
