# kaos-source

`kaos-source` is the source discovery and materialization layer for KAOS. It sits above `kaos-core`, keeps discovery metadata-first, and turns explicit fetch/materialize requests into durable KAOS artifacts.

## Current Scope

The first slice is intentionally local-first:

- typed source locators, descriptors, previews, pages, materializations, and jobs
- connector protocol plus `SourceService`
- filesystem, archive, memory, and HTTP connectors
- browser-rendered fetches via an optional Playwright-backed connector
- cursor-based discovery without eager body loading
- explicit artifact-backed materialization through `kaos-core`
- policy-aware HTTP fetches with bounded preview and streamed materialization

Deferred after this slice:

- browser automation
- search discovery
- batch ledgers and resumable runs
- MCP-facing tools in downstream modules

Browser support is optional and expects the `browser` extra plus Playwright browser binaries:

```bash
uv sync --python 3.13 --group dev --extra browser
uv run --python 3.13 playwright install chromium
```

## CLI

```bash
kaos-source discover ./data/ --recursive --pattern "*.pdf"  # list sources
kaos-source preview document.pdf --max-bytes 2048           # bounded preview
kaos-source info document.pdf --json                        # source metadata
kaos-source materialize document.pdf --name my-artifact     # stage to artifact store
kaos-source inspect-archive bundle.zip                      # list archive members
```

All commands support `--json` for structured output.

## Development

```bash
uv sync --python 3.13 --group dev
uv run --python 3.13 ruff format kaos_source tests
uv run --python 3.13 ruff check --fix kaos_source tests
uv run --python 3.13 ty check kaos_source tests
uv run --python 3.13 pytest -q
```

## Design Notes

- `kaos-source` does not reintroduce Kelvin-style `SourceObject`.
- Discovery and preview are metadata-first and bounded.
- Large bodies move through `kaos-core` artifact manifests and lazy body handles.
- `kaos-mcp` remains the protocol adapter that exposes materialized artifacts over MCP.
