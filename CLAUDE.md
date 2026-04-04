# kaos-source Development Notes

## Design Principles

- Keep discovery metadata-first.
- Do not inline large bodies.
- Materialization must flow through `kaos-core` artifacts.
- Follow the KAOS Python QA process: `ruff format`, `ruff check --fix`, `ty check`, `pytest`.

## Architecture

```
SourceLocator -> SourceService -> SourceConnector (filesystem/archive/http/browser/memory)
    -> describe() -> SourceDescriptor (metadata only)
    -> discover() -> SourcePage (paginated items)
    -> preview()  -> SourcePreview (bounded read)
    -> materialize() -> SourceMaterialization (artifact)
```

## Connectors

| Connector | Kind | Purpose |
|-----------|------|---------|
| FilesystemConnector | filesystem | Local files and directories |
| ArchiveConnector | archive | ZIP and TAR archives |
| HttpConnector | http | HTTP/HTTPS URL fetching |
| BrowserConnector | browser | Playwright-based rendering (raw HTML materialization) |
| MemoryConnector | memory | In-memory testing |

**Note:** BrowserConnector is a stateless materialization wrapper (launch browser → navigate → get HTML → close). For interactive browser workflows (click, fill, multi-step), use kaos-web's 18 browser interaction tools instead. The two are architecturally separate: kaos-source produces artifacts, kaos-web produces ContentDocument AST.

## Data Retrieval Connectors

### Federal Register (no auth)
- 4 MCP tools: `kaos-source-fr-search`, `kaos-source-fr-get-document`, `kaos-source-fr-get-content`, `kaos-source-fr-agencies`
- Settings: `KaosSourceFRSettings` (`KAOS_SOURCE_FR_` env prefix)
- API: `https://www.federalregister.gov/api/v1`

### eCFR (no auth)
- 4 MCP tools: `kaos-source-ecfr-titles`, `kaos-source-ecfr-structure`, `kaos-source-ecfr-content`, `kaos-source-ecfr-search-structure`
- Settings: `KaosSourceECFRSettings` (`KAOS_SOURCE_ECFR_` env prefix)
- API: `https://www.ecfr.gov/api`

### GovInfo (API key required)
- 3 MCP tools: `kaos-source-govinfo-search`, `kaos-source-govinfo-package`, `kaos-source-govinfo-collections`
- Settings: `KaosSourceGovInfoSettings` (`KAOS_SOURCE_GOVINFO_` env prefix)
- API key: `KAOS_SOURCE_GOVINFO_API_KEY` (or legacy `GOVINFO_API_KEY`), uses `SecretStr`
- Free key: https://api.data.gov/signup/
- API: `https://api.govinfo.gov`

### EDGAR (User-Agent required, no API key)
- 3 MCP tools: `kaos-source-edgar-search`, `kaos-source-edgar-company`, `kaos-source-edgar-lookup`
- Settings: `KaosSourceEdgarSettings` (`KAOS_SOURCE_EDGAR_` env prefix)
- SEC requires `User-Agent: "Company email@co.com"` format (default: `273Ventures research@273ventures.com`)
- Rate limit: 10 req/s
- APIs: `efts.sec.gov` (search), `data.sec.gov` (submissions), `sec.gov` (tickers)

### PACER (local parser, no auth)
- 2 MCP tools: `kaos-source-pacer-parse`, `kaos-source-pacer-filter-entries`
- Parses saved PACER docket HTML files — no network access, no PACER account needed
- Requires `[pacer]` extra (lxml)

## Core MCP Tools (6)

All tools follow kaos-core `KaosTool` ABC. Register with `register_source_tools(runtime)`.

| Tool | Name | Read-Only | Open-World | Purpose |
|------|------|-----------|------------|---------|
| DiscoverSourcesTool | `kaos-source-discover` | Yes | No | List files in directory/archive |
| DescribeSourceTool | `kaos-source-describe` | Yes | No | Get file metadata |
| PreviewSourceTool | `kaos-source-preview` | Yes | No | Bounded content preview |
| MaterializeSourceTool | `kaos-source-materialize` | No | No | Copy to artifact store |
| FetchURLTool | `kaos-source-fetch-url` | No | Yes | Fetch from HTTP URL |
| InspectArchiveTool | `kaos-source-inspect-archive` | Yes | No | List archive members |

## Credentials & Configuration

All connector settings use `ModuleSettings` (pydantic-settings) with env var + `.env` file support.

```bash
# Required for GovInfo only — all others work without keys
export KAOS_SOURCE_GOVINFO_API_KEY=your-key-here

# Optional: customize EDGAR User-Agent (SEC requires company + email)
export KAOS_SOURCE_EDGAR_USER_AGENT="YourCompany contact@company.com"

# Optional: adjust timeouts (all connectors)
export KAOS_SOURCE_FR_TIMEOUT=60.0
export KAOS_SOURCE_ECFR_CONTENT_TIMEOUT=600.0
```

See `.env.example` for all available env vars. Test credentials go in `.env.test` (gitignored).

Settings flow: env vars → `ModuleSettings` subclass → passed to connector functions by MCP tools.

## MCP Serve

`kaos-source-serve [--http] [--host HOST] [--port PORT] [--debug]`

Also available via: `kaos-mcp serve --module source`

## CLI

- `kaos-source discover PATH [--recursive] [--limit 50] [--pattern "*.pdf"] [--json]`
- `kaos-source preview FILE [--max-bytes 1024] [--json]`
- `kaos-source info FILE [--json]`
- `kaos-source materialize FILE [--name NAME] [--json]`
- `kaos-source inspect-archive ARCHIVE [--json]`

## Typed Settings

Core connector settings in `kaos_source.settings`:

- **`KaosSourceHttpSettings`** — HTTP connector (`KAOS_SOURCE_HTTP_` prefix). Includes retry backoff tuning.
- **`KaosSourceBrowserSettings`** — Browser connector (`KAOS_SOURCE_BROWSER_` prefix)

Data retrieval settings in their respective connector modules:

- **`KaosSourceFRSettings`** — Federal Register (`KAOS_SOURCE_FR_` prefix)
- **`KaosSourceECFRSettings`** — eCFR (`KAOS_SOURCE_ECFR_` prefix)
- **`KaosSourceGovInfoSettings`** — GovInfo (`KAOS_SOURCE_GOVINFO_` prefix, `SecretStr` for API key)
- **`KaosSourceEdgarSettings`** — EDGAR (`KAOS_SOURCE_EDGAR_` prefix)

## QA Process

```bash
ruff format kaos_source/ tests/
ruff check --fix kaos_source/ tests/
ty check kaos_source/ tests/
pytest tests/ -v
```

Integration tests (require network + keys): `pytest tests/integration/ -v`
For GovInfo integration tests: `GOVINFO_API_KEY=xxx pytest tests/integration/test_govinfo.py -v`

## Rules

- **Never add AGPL/GPL dependencies.** This is a proprietary codebase.
- Tool error messages must include recovery guidance (what went wrong + how to fix + alternative).
- All tools must have `ToolAnnotations` set explicitly (not None).
- API keys must use `SecretStr` to prevent accidental logging.
- All MCP tools must thread `ModuleSettings` to connector functions (no hardcoded defaults bypassing env vars).
- Errors to stderr with non-zero exit, output to stdout.
