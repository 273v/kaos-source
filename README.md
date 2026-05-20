# kaos-source

> **Part of [Kelvin Agentic OS](https://kelvin.legal) (KAOS)** — open agentic
> infrastructure for legal work, built by
> [273 Ventures](https://273ventures.com).
> See the [full KAOS package map](https://github.com/273v) for the rest of the stack.

[![PyPI - Version](https://img.shields.io/pypi/v/kaos-source)](https://pypi.org/project/kaos-source/)
[![Python](https://img.shields.io/pypi/pyversions/kaos-source)](https://pypi.org/project/kaos-source/)
[![License](https://img.shields.io/pypi/l/kaos-source)](https://github.com/273v/kaos-source/blob/main/LICENSE)
[![CI](https://github.com/273v/kaos-source/actions/workflows/ci.yml/badge.svg)](https://github.com/273v/kaos-source/actions/workflows/ci.yml)

`kaos-source` is the **source discovery and materialization** layer for KAOS —
filesystem, archive, HTTP, and browser transport connectors, plus REST clients
for the Federal Register, eCFR, EDGAR, GovInfo, and GLEIF, and forensic
parsers for VCard, EML / MBOX email, PACER docket HTML, and image EXIF.

It is the layer between "I have a URL / path / docket number" and "give me a
typed `SourceDescriptor` plus an artifact handle in `kaos-core`'s VFS." Every
fetch goes through a strict-by-default SSRF guard, every response body is
size-capped, every archive iteration enforces decompression-ratio and
symlink protection. Configurability lives in `KAOS_SECURITY_*` and
`KAOS_SOURCE_*` env vars.

The base install carries only `httpx`, `kaos-core`, and `pydantic` — most of
the heavy lifting (lxml, pillow, playwright, kaos-content, kaos-nlp-core)
is gated behind opt-in extras (`[browser]`, `[content]`, `[pacer]`).

## Install

```bash
uv add "kaos-source>=0.1.0"
# or
pip install "kaos-source>=0.1.0"
```

Optional extras (all additive — none of the base functionality requires them):

```bash
uv add 'kaos-source[browser]>=0.1.0'   # Playwright-backed browser fetches
uv add 'kaos-source[content]>=0.1.0'   # parse-into-ContentDocument bridges
uv add 'kaos-source[pacer]>=0.1.0'     # lxml-backed PACER docket parser
```

`kaos-source` requires Python **3.13** or newer.

## Quick start

Discover, preview, and materialize a local file through the in-memory
`SourceService`:

```python
import asyncio
from pathlib import Path

from kaos_core import KaosContext, KaosRuntime
from kaos_core.protocol.roots import Root
from kaos_source import (
    SourceDiscoverOptions,
    SourceLocator,
    SourcePreviewOptions,
    SourceService,
)


async def main() -> None:
    runtime = KaosRuntime()
    service = SourceService()  # registers the five default connectors
    workspace = Path.cwd()
    context = KaosContext.create(
        session_id="quickstart",
        runtime=runtime,
        roots=[Root(uri=workspace.as_uri(), name="cwd")],
    )

    page = await service.discover(
        SourceLocator.filesystem(workspace),
        context,
        SourceDiscoverOptions(limit=5, patterns=["*.py"]),
    )
    print([item.name for item in page.items])

    if page.items:
        preview = await service.preview(
            page.items[0].locator,
            context,
            SourcePreviewOptions(max_bytes=120),
        )
        print(preview.text_preview)


asyncio.run(main())
```

The same `SourceService` API also handles `archive://`, `http(s)://`,
`browser://`, and `memory://` locators — only the `Root` allowlist and the
SSRF guard change behaviour per scheme.

## Concepts

The package is organized around three layers — contracts, runtime, and
domain-specific catalogues — that auto-register on import.

| Concept | What it is |
|---|---|
| **`SourceConnector` / `ApiConnector` / `SourceParser`** | Three ABCs in `kaos_source.base`. Connectors handle URI-addressed transports (filesystem, archive, HTTP, browser, memory). API connectors handle parameterized REST APIs (Federal Register, eCFR, EDGAR, GovInfo, GLEIF). Parsers handle byte-stream formats (VCard, EML, MBOX, PACER, EXIF). |
| **`SourceLocator` / `SourceDescriptor`** | The locator is the addressable input (`SourceLocator.http("https://…")`, `SourceLocator.archive_member(path, "docs/x.pdf")`). The descriptor is the metadata-first response: name, MIME, size, provenance, capability flags. Discovery is metadata-first by design — bodies don't load until materialize. |
| **`SourceService`** | Runtime that routes operations across registered connectors. Subclasses of `SourceConnector` register themselves at import time via `default_connector_registry`. Custom connectors register explicitly with `default_connector_registry.register(...)`. |
| **`SourceMaterialization`** | The artifact-handle return type from `service.materialize(...)`. Bodies move through `kaos-core`'s artifact store, never inline. The descriptor's `metadata` carries `archive_format`, `cik`, `lei`, etc. depending on the connector. |
| **`KaosSourceHttpSettings` and friends** | Per-connector `ModuleSettings` subclasses with the `KAOS_SOURCE_*` env prefix. Each carries connector-specific knobs (timeout, retry, allowed_hosts, EDGAR User-Agent, GovInfo SecretStr API key). All read from environment at edge of the call graph and thread through to the connector. |
| **SSRF + size-cap guards** | The HTTP connector and every API client run through `kaos_core.security.validate_outbound_url` (per-request, including each redirect hop) and `kaos_core.security.read_capped_json` (streamed, with `Content-Length` pre-flight + running byte budget). Strict-by-default; configurable via `KAOS_SECURITY_*` env vars. |

## CLI

`kaos-source` ships a `kaos-source` administrative CLI plus a
`kaos-source-serve` MCP launcher. Every structured command supports
`--json` for machine-readable output:

```bash
kaos-source discover ./data/ --recursive --pattern "*.pdf"  # list sources
kaos-source preview document.pdf --max-bytes 2048           # bounded preview
kaos-source info document.pdf --json                        # source metadata
kaos-source materialize document.pdf --name my-artifact     # stage to artifact store
kaos-source inspect-archive bundle.zip                      # list archive members

kaos-source-serve --http --port 8765                        # MCP server (stdio default)
```

## Compatibility & status

| Aspect | |
|---|---|
| **Python** | 3.13, 3.14 (informational matrix entries for 3.14t free-threaded and 3.15-dev) |
| **OS** | Linux, macOS, Windows (pure-Python wheel; no native code) |
| **Maturity** | 0.1.0 GA. The public API is documented in `kaos_source.__all__` (56 symbols). |
| **Stability policy** | Pre-1.0: minor bumps may change behaviour. Every change is documented in [`CHANGELOG.md`](CHANGELOG.md). The MCP tool surface, `KAOS_SOURCE_*` and `KAOS_SECURITY_*` environment-variable namespaces are public API. |
| **Test coverage** | 411 unit tests across connectors, API clients, parsers, settings, and security regressions. Live integration tests gated behind `--include-live`. |
| **Type checker** | Validated with [`ty`](https://docs.astral.sh/ty/), Astral's Python type checker. |

## Documentation

Per-package reference: see in-tree docstrings and
[CHANGELOG.md](CHANGELOG.md).

Cross-cutting KAOS guides (agentic patterns, persona presets, settings
policy, citations, MCP data flow, migration to 0.1.0 GA) live in
[`kaos-modules/docs/guides/`](https://github.com/273v/kaos-modules/tree/main/docs/guides).

## Companion packages

`kaos-source` is one of the packages in the
[Kelvin Agentic OS](https://kelvin.legal). The broader stack:

| Package | Layer | What it does |
|---|---|---|
| [`kaos-core`](https://github.com/273v/kaos-core) | Core | Foundational runtime, MCP-native types, registries, execution engine, VFS |
| [`kaos-content`](https://github.com/273v/kaos-content) | Core | Typed document AST: Block/Inline, provenance, views |
| [`kaos-mcp`](https://github.com/273v/kaos-mcp) | Bridge | FastMCP server, `kaos` management CLI, MCP resource templates |
| [`kaos-pdf`](https://github.com/273v/kaos-pdf) | Extraction | PDF → AST with provenance |
| [`kaos-web`](https://github.com/273v/kaos-web) | Extraction | Web extraction, browser automation, search, domain intelligence |
| [`kaos-office`](https://github.com/273v/kaos-office) | Extraction | DOCX / PPTX / XLSX readers + writers to AST |
| [`kaos-tabular`](https://github.com/273v/kaos-tabular) | Extraction | DuckDB-powered SQL analytics |
| [`kaos-source`](https://github.com/273v/kaos-source) | Data | Government + financial data connectors (Federal Register, eCFR, EDGAR, GovInfo, PACER, GLEIF) |
| [`kaos-llm-client`](https://github.com/273v/kaos-llm-client) | LLM | Multi-provider LLM transport |
| [`kaos-llm-core`](https://github.com/273v/kaos-llm-core) | LLM | Typed LLM programming (Signatures, Programs, Optimizers) |
| [`kaos-nlp-core`](https://github.com/273v/kaos-nlp-core) | Primitives (Rust) | High-performance NLP primitives |
| [`kaos-nlp-transformers`](https://github.com/273v/kaos-nlp-transformers) | ML | Dense embeddings + retrieval |
| [`kaos-graph`](https://github.com/273v/kaos-graph) | Primitives (Rust) | Graph algorithms + RDF/SPARQL |
| [`kaos-ml-core`](https://github.com/273v/kaos-ml-core) | Primitives (Rust) | Classical ML on the document AST |
| [`kaos-citations`](https://github.com/273v/kaos-citations) | Legal | Legal citation extraction, resolution, verification |
| [`kaos-agents`](https://github.com/273v/kaos-agents) | Agentic | Agent runtime, memory, recipes |
| [`kaos-reference`](https://github.com/273v/kaos-reference) | Sample | Reference module for module authors |

Packages depend on `kaos-core`; everything else is opt-in. Mix and match the
ones you need.

## Development

```bash
git clone https://github.com/273v/kaos-source
cd kaos-source
uv sync --group dev
```

Install pre-commit hooks (recommended — they run the same checks as CI on
every commit, scoped to staged files):

```bash
uvx pre-commit install
uvx pre-commit run --all-files     # one-time full sweep
```

Manual QA commands (the same set CI runs):

```bash
uv run ruff format --check kaos_source tests
uv run ruff check kaos_source tests
uv run ty check kaos_source tests
uv run pytest tests/unit --no-cov
```

## Build from source

```bash
uv build
uv pip install dist/*.whl
```

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md)
for setup, quality gates, pull request expectations, and engineering
standards. By contributing you agree to follow the
[project conduct expectations](CODE_OF_CONDUCT.md) and certify the
[Developer Certificate of Origin v1.1](https://developercertificate.org/) —
sign every commit with `git commit -s`. Please open an issue before starting
on a non-trivial change so we can align on scope.

## Security

For security issues, **please do not file a public issue**. Report privately
via [GitHub Private Vulnerability Reporting](https://github.com/273v/kaos-source/security/advisories/new)
or email **security@273ventures.com**. See [SECURITY.md](SECURITY.md) for the
full disclosure policy.

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).

Copyright 2026 [273 Ventures LLC](https://273ventures.com).
Built for [kelvin.legal](https://kelvin.legal).
