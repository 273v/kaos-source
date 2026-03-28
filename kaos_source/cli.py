"""Command-line interface for kaos-source.

Every command supports --json for structured output (pipe-friendly).
Without --json, output is human-readable.

Usage:
    kaos-source discover PATH [--recursive] [--limit 50] [--pattern "*.pdf"] [--json]
    kaos-source preview LOCATOR [--max-bytes 1024] [--json]
    kaos-source info LOCATOR [--json]
    kaos-source materialize LOCATOR [--name ARTIFACT_NAME] [--json]
    kaos-source inspect-archive ARCHIVE [--json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any


def main(argv: list[str] | None = None) -> None:
    """Entry point for kaos-source CLI."""
    parser = argparse.ArgumentParser(
        prog="kaos-source", description="Source discovery and materialization"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # discover
    p_discover = sub.add_parser("discover", help="Discover sources in a directory or archive")
    p_discover.add_argument("path", type=Path, help="Directory or archive path")
    p_discover.add_argument(
        "--recursive", action="store_true", default=True, help="Recurse into subdirectories"
    )
    p_discover.add_argument(
        "--no-recursive", action="store_true", help="Disable recursive discovery"
    )
    p_discover.add_argument("--limit", type=int, default=50, help="Maximum items to return")
    p_discover.add_argument(
        "--pattern", action="append", dest="patterns", help="Glob pattern filter (repeatable)"
    )
    p_discover.add_argument("--json", action="store_true", help="Structured JSON output")

    # preview
    p_preview = sub.add_parser("preview", help="Preview source content")
    p_preview.add_argument("locator", type=Path, help="File path to preview")
    p_preview.add_argument(
        "--max-bytes", type=int, default=1024, help="Maximum bytes to preview (default: 1024)"
    )
    p_preview.add_argument("--json", action="store_true", help="Structured JSON output")

    # info
    p_info = sub.add_parser("info", help="Show source metadata")
    p_info.add_argument("locator", type=Path, help="File path to describe")
    p_info.add_argument("--json", action="store_true", help="Structured JSON output")

    # materialize
    p_materialize = sub.add_parser("materialize", help="Materialize source to artifact store")
    p_materialize.add_argument("locator", type=Path, help="File path to materialize")
    p_materialize.add_argument("--name", default=None, help="Artifact name override")
    p_materialize.add_argument("--json", action="store_true", help="Structured JSON output")

    # inspect-archive
    p_archive = sub.add_parser("inspect-archive", help="List contents of an archive")
    p_archive.add_argument("archive", type=Path, help="Archive file path")
    p_archive.add_argument("--json", action="store_true", help="Structured JSON output")

    args = parser.parse_args(argv)

    handlers = {
        "discover": _cmd_discover,
        "preview": _cmd_preview,
        "info": _cmd_info,
        "materialize": _cmd_materialize,
        "inspect-archive": _cmd_inspect_archive,
    }

    try:
        handlers[args.command](args)
    except FileNotFoundError as exc:
        _error(str(exc))
    except Exception as exc:
        _error(str(exc))


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _json_out(data: dict[str, Any]) -> None:
    """Print structured JSON to stdout."""
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _error(msg: str) -> None:
    """Print error to stderr and exit."""
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


def _format_size(size: int | None) -> str:
    """Format byte size for human display."""
    if size is None:
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _make_context() -> Any:
    """Create a minimal KaosContext for CLI use."""
    from kaos_core import KaosContext, KaosRuntime

    runtime = KaosRuntime.default()
    return KaosContext.create(session_id="cli", runtime=runtime)


def _make_service() -> Any:
    """Create a SourceService with filesystem and archive connectors."""
    from kaos_source import ArchiveConnector, FilesystemConnector, SourceService

    return SourceService(connectors=[FilesystemConnector(), ArchiveConnector()])


def _validate_path(path: Path) -> Path:
    """Validate that path exists and return resolved path."""
    path = path.resolve()
    if not path.exists():
        msg = f"Path not found: {path}"
        raise FileNotFoundError(msg)
    return path


def _descriptor_to_dict(desc: Any) -> dict[str, Any]:
    """Convert a SourceDescriptor to a JSON-friendly dict."""
    return {
        "source_id": desc.source_id,
        "name": desc.name,
        "mime_type": desc.mime_type,
        "size": desc.size,
        "source_kind": str(desc.source_kind),
        "created_at": desc.created_at,
        "modified_at": desc.modified_at,
        "metadata": desc.metadata,
    }


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def _cmd_discover(args: argparse.Namespace) -> None:
    asyncio.run(_async_cmd_discover(args))


async def _async_cmd_discover(args: argparse.Namespace) -> None:
    from kaos_source import SourceDiscoverOptions, SourceLocator

    path = _validate_path(args.path)
    recursive = not args.no_recursive

    if path.is_file() and path.suffix in {".zip", ".tar", ".gz", ".bz2", ".tgz", ".tar.gz"}:
        locator = SourceLocator.archive(path)
    else:
        locator = SourceLocator.filesystem(path)

    service = _make_service()
    context = _make_context()

    options = SourceDiscoverOptions(
        recursive=recursive,
        limit=args.limit,
        patterns=args.patterns or [],
    )
    page = await service.discover(locator, context, options)

    if args.json:
        _json_out(
            {
                "command": "discover",
                "path": str(path),
                "total": len(page.items),
                "items": [_descriptor_to_dict(item) for item in page.items],
            }
        )
        return

    if not page.items:
        print(f"No sources found in {path}")
        return

    # Tabular output
    name_width = max(len(item.name) for item in page.items)
    name_width = max(name_width, 4)  # minimum "Name" header width
    name_width = min(name_width, 60)  # cap width

    print(f"{'Name':<{name_width}}  {'Size':>10}  {'Type'}")
    print(f"{'-' * name_width}  {'-' * 10}  {'-' * 20}")
    for item in page.items:
        name_display = item.name[:name_width]
        size_display = _format_size(item.size)
        mime_display = item.mime_type or "-"
        print(f"{name_display:<{name_width}}  {size_display:>10}  {mime_display}")

    print(f"\n{len(page.items)} item(s) found")


def _cmd_preview(args: argparse.Namespace) -> None:
    asyncio.run(_async_cmd_preview(args))


async def _async_cmd_preview(args: argparse.Namespace) -> None:
    from kaos_source import SourceLocator, SourcePreviewOptions

    path = _validate_path(args.locator)
    if not path.is_file():
        _error(f"Not a file: {path}")

    locator = SourceLocator.filesystem(path)
    service = _make_service()
    context = _make_context()

    options = SourcePreviewOptions(max_bytes=args.max_bytes)
    preview = await service.preview(locator, context, options)

    if args.json:
        result: dict[str, Any] = {
            "command": "preview",
            "locator": str(path),
            "truncated": preview.truncated,
            "size": preview.size,
            "mime_type": preview.mime_type,
        }
        if preview.text_preview is not None:
            result["text"] = preview.text_preview
        elif preview.binary_preview_base64 is not None:
            result["binary_base64"] = preview.binary_preview_base64
        _json_out(result)
        return

    if preview.text_preview is not None:
        print(preview.text_preview)
        if preview.truncated:
            print(f"\n--- truncated (showing {args.max_bytes} bytes of {preview.size}) ---")
    elif preview.binary_preview_base64 is not None:
        print(f"[Binary content, {_format_size(preview.size)}]")
        if preview.truncated:
            print(f"(showing first {args.max_bytes} bytes)")
    else:
        print("No preview available")


def _cmd_info(args: argparse.Namespace) -> None:
    asyncio.run(_async_cmd_info(args))


async def _async_cmd_info(args: argparse.Namespace) -> None:
    from kaos_source import SourceLocator

    path = _validate_path(args.locator)
    if not path.is_file():
        _error(f"Not a file: {path}")

    locator = SourceLocator.filesystem(path)
    service = _make_service()
    context = _make_context()

    desc = await service.describe(locator, context)

    if args.json:
        _json_out(
            {
                "command": "info",
                "locator": str(path),
                **_descriptor_to_dict(desc),
            }
        )
        return

    print(f"Name:       {desc.name}")
    print(f"Kind:       {desc.source_kind}")
    print(f"MIME type:  {desc.mime_type or '-'}")
    print(f"Size:       {_format_size(desc.size)}")
    if desc.created_at:
        print(f"Created:    {desc.created_at}")
    if desc.modified_at:
        print(f"Modified:   {desc.modified_at}")
    if desc.metadata:
        print(f"Metadata:   {json.dumps(desc.metadata, indent=2)}")


def _cmd_materialize(args: argparse.Namespace) -> None:
    asyncio.run(_async_cmd_materialize(args))


async def _async_cmd_materialize(args: argparse.Namespace) -> None:
    from kaos_source import SourceLocator, SourceMaterializeOptions

    path = _validate_path(args.locator)
    if not path.is_file():
        _error(f"Not a file: {path}")

    locator = SourceLocator.filesystem(path)
    service = _make_service()
    context = _make_context()

    options = SourceMaterializeOptions(artifact_name=args.name)
    result = await service.materialize(locator, context, options)

    if args.json:
        _json_out(
            {
                "command": "materialize",
                "locator": str(path),
                "artifact_id": result.artifact_ref.artifact_id,
                "bytes_written": result.bytes_written,
                "retention_policy": str(result.retention_policy),
            }
        )
        return

    print(f"Materialized: {path.name}")
    print(f"Artifact ID:  {result.artifact_ref.artifact_id}")
    print(f"Bytes:        {_format_size(result.bytes_written)}")
    print(f"Retention:    {result.retention_policy}")


def _cmd_inspect_archive(args: argparse.Namespace) -> None:
    asyncio.run(_async_cmd_inspect_archive(args))


async def _async_cmd_inspect_archive(args: argparse.Namespace) -> None:
    from kaos_source import SourceDiscoverOptions, SourceLocator

    path = _validate_path(args.archive)
    if not path.is_file():
        _error(f"Not a file: {path}")

    locator = SourceLocator.archive(path)
    service = _make_service()
    context = _make_context()

    options = SourceDiscoverOptions(recursive=True, limit=500)
    page = await service.discover(locator, context, options)

    if args.json:
        _json_out(
            {
                "command": "inspect-archive",
                "archive": str(path),
                "total": len(page.items),
                "members": [_descriptor_to_dict(item) for item in page.items],
            }
        )
        return

    if not page.items:
        print(f"No members found in {path.name}")
        return

    name_width = max(len(item.name) for item in page.items)
    name_width = max(name_width, 4)
    name_width = min(name_width, 60)

    print(f"Archive: {path.name}")
    print(f"{'Name':<{name_width}}  {'Size':>10}  {'Type'}")
    print(f"{'-' * name_width}  {'-' * 10}  {'-' * 20}")
    for item in page.items:
        name_display = item.name[:name_width]
        size_display = _format_size(item.size)
        mime_display = item.mime_type or "-"
        print(f"{name_display:<{name_width}}  {size_display:>10}  {mime_display}")

    print(f"\n{len(page.items)} member(s)")
