# Agent Guidance

## Scope

This file is the canonical coding-agent guidance for this repository. Apply it to the whole tree unless a more specific `AGENTS.md` appears in a subdirectory.

Keep changes focused, public-repository safe, and aligned with:

- [CONTRIBUTING.md](CONTRIBUTING.md)
- [Python design and architecture](docs/standards/python-design-and-architecture.md)
- [Code quality standards](docs/standards/code-quality-standards.md)
- [Engineering process](docs/standards/engineering-process.md)
- [Tests, fixtures, and CI](docs/standards/tests-fixtures-ci.md)

Prefer linking to those standards over duplicating their full detail here.

## Project Identity

`kaos-source` is the source discovery and materialization package for KAOS. The distribution name is `kaos-source`; the import package is `kaos_source`.

The repository is pure Python and requires Python 3.13 or newer. It publishes the `kaos-source` administrative CLI and `kaos-source-serve` MCP launcher. Public behavior includes Python APIs, CLI commands and JSON output, MCP tools and schemas, environment variables, settings models, and serialized result shapes.

## Setup

Use `uv` for environments, dependency resolution, builds, and command execution:

```bash
uv sync --group dev
```

Keep base dependencies minimal. Optional integrations belong behind extras and lazy imports.

## Local Checks

Run the cheapest relevant checks for the change. For normal code changes, use:

```bash
uv run ruff format --check kaos_source tests
uv run ruff check kaos_source tests
uv run ty check kaos_source tests
uv run pytest tests/unit --no-cov
```

Type checking uses `ty`, not mypy. Use `# ty: ignore[...]` only when necessary and narrowly justified.

For packaging, metadata, README rendering, or release-behavior changes, also run:

```bash
uv build
uvx --from twine twine check --strict dist/*
```

If a check is not practical, state the reason in the final response or PR notes.

## Architecture Rules

Respect the package's three main extension surfaces:

- `kaos_source.base`: connector, API connector, parser, metadata, capability, and protocol contracts.
- `kaos_source.connectors`: URI-addressed transports such as filesystem, archives, HTTP, browser, and memory.
- `kaos_source.apis` and `kaos_source.parsers`: provider clients and domain parsers for Federal Register, eCFR, EDGAR, GovInfo, GLEIF, PACER, files, archives, email, vCard, and images.

Discovery and preview are metadata-first. Do not materialize bodies until the caller asks for materialization. Keep previews bounded and deterministic, and route bodies through the artifact/materialization path instead of returning large inline payloads.

Preserve connector boundaries:

- Filesystem and archive connectors enforce path, traversal, symlink, decompression-ratio, recursion, and size protections.
- HTTP and browser connectors enforce URL validation, redirect validation, timeouts, rate limits where applicable, and response-size caps.
- Federal Register, eCFR, EDGAR, GovInfo, and GLEIF clients keep provider-specific settings, auth, pagination, response models, and error handling inside their connector/client boundaries.
- PACER, email, archive, file, and image parsers treat inputs as untrusted and keep parsing limits explicit.

Keep public CLI, MCP, JSON, schema, environment-variable, and settings behavior stable. User-visible contract changes require tests and changelog consideration.

## Testing

Prefer deterministic offline tests. Unit tests must not require network, credentials, local services, or large downloads. Network and live-provider tests must be explicit opt-ins and must be marked so normal CI can exclude them.

Fixtures must be redistributable, documented, small enough for normal repository use, and free of secrets, privileged content, customer data, and PII. Do not add unknown-license fixture data.

Security-sensitive behavior needs accepted and rejected cases with realistic inputs, especially for URLs, paths, archives, parser payloads, credentials, redirects, size caps, and materialization.

## Security

Never commit secrets, tokens, private keys, credentials, `.env` files, or sensitive fixture data. Use secret-aware types for credentials and redact secrets in logs, errors, CLI output, JSON output, test output, and MCP responses.

Preserve protections for:

- URL validation and SSRF resistance.
- Path normalization and traversal prevention.
- Archive member safety, decompression limits, and symlink handling.
- Request timeouts, retry behavior, provider rate limits, and size caps.
- Parser robustness for malformed HTML, email, archives, metadata, and images.

Live credentials and provider access must be opt-in. Do not make default tests depend on network access or real provider accounts.

## Commits, PRs, And Releases

Follow conventional commit style and sign commits with `git commit -s`. Keep PRs focused and explain what changed, why, how it was tested, and whether public API, CLI, MCP schema, package metadata, fixtures, security behavior, or release artifacts are affected.

Before committing, fetch the latest `origin`, rebase when needed, run `git diff --check`, and run practical local checks. Do not force-push unless a maintainer explicitly requests it.

Update `CHANGELOG.md` for user-visible changes, public API changes, CLI or MCP behavior changes, schema changes, package metadata changes, security behavior changes, and deprecations. Do not edit release metadata or generated files unless the task explicitly requires it.
