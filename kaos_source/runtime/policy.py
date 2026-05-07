"""Path / URI policy helpers — root-allowlist enforcement and existence checks.

Two families of guard functions:

- **Root policy** — :func:`assert_roots_allow_path` /
  :func:`assert_roots_allow_uri` enforce the MCP-style "roots" allowlist.
  When a context provides root entries, every accessed file path or URI
  must fall under one of them; otherwise we raise
  :class:`SourcePolicyError`.
- **Existence checks** — :func:`ensure_file_exists` /
  :func:`ensure_directory` / :func:`ensure_regular_file` raise
  agent-friendly :class:`SourceNotFoundError` /
  :class:`SourceValidationError` instead of bare :class:`OSError`.

Plus :func:`path_matches_patterns` for fnmatch-style filtering used by
``discover()`` glob filters.
"""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse, urlsplit

from kaos_core.protocol.roots import Root

from kaos_source.errors import (
    SourceNotFoundError,
    SourcePolicyError,
    SourceValidationError,
)


def path_matches_patterns(path: str, patterns: list[str]) -> bool:
    """True when ``path`` matches any of ``patterns`` (or no patterns given).

    Each pattern is checked against the full path AND the basename
    (``PurePosixPath(path).name``) — so ``*.pdf`` matches both
    ``foo.pdf`` and ``a/b/foo.pdf``.
    """
    if not patterns:
        return True
    return any(
        fnmatch(path, pattern) or fnmatch(PurePosixPath(path).name, pattern) for pattern in patterns
    )


def _root_path(root: Root) -> Path | None:
    """Resolve a ``file://`` root URI to an absolute Path. Non-file roots → None."""
    parsed = urlparse(root.uri)
    if parsed.scheme != "file":
        return None
    return Path(unquote(parsed.path or "/")).resolve()


def assert_roots_allow_path(path: Path, roots: list[Root] | None) -> None:
    """Raise :class:`SourcePolicyError` if ``path`` is outside every file root.

    ``roots=None`` or empty short-circuits to allow (no policy in effect).
    """
    if not roots:
        return
    resolved_path = path.resolve()
    root_paths = [root_path for root in roots if (root_path := _root_path(root)) is not None]
    if not root_paths:
        raise SourcePolicyError("Source access denied by roots policy", path=str(resolved_path))
    for root_path in root_paths:
        try:
            resolved_path.relative_to(root_path)
        except ValueError:
            continue
        return
    raise SourcePolicyError("Source access denied by roots policy", path=str(resolved_path))


def assert_roots_allow_uri(uri: str, roots: list[Root] | None, *, schemes: set[str]) -> None:
    """Raise :class:`SourcePolicyError` if ``uri`` is outside every relevant root.

    Only roots whose scheme is in ``schemes`` (e.g. ``{"http", "https"}``)
    participate in the check. If no relevant roots exist, the check is
    skipped (different scheme families are independent).
    """
    if not roots:
        return

    parsed_uri = urlsplit(uri)
    relevant_roots = [root for root in roots if urlsplit(root.uri).scheme.lower() in schemes]
    if not relevant_roots:
        return

    request_scheme = parsed_uri.scheme.lower()
    request_netloc = parsed_uri.netloc.lower()
    request_path = PurePosixPath(parsed_uri.path or "/").as_posix()

    for root in relevant_roots:
        parsed_root = urlsplit(root.uri)
        root_scheme = parsed_root.scheme.lower()
        root_netloc = parsed_root.netloc.lower()
        root_path = PurePosixPath(parsed_root.path or "/").as_posix()
        if request_scheme != root_scheme or request_netloc != root_netloc:
            continue
        normalized_root = root_path.rstrip("/") or "/"
        if normalized_root == "/":
            return
        if request_path == normalized_root or request_path.startswith(f"{normalized_root}/"):
            return

    raise SourcePolicyError("Source access denied by roots policy", uri=uri)


def ensure_file_exists(path: Path) -> Path:
    """Resolve ``path`` and raise :class:`SourceNotFoundError` if absent."""
    resolved = path.resolve()
    if not resolved.exists():
        raise SourceNotFoundError("Source path does not exist", path=str(resolved))
    return resolved


def ensure_directory(path: Path) -> Path:
    """Resolve ``path`` and raise unless it points to a directory."""
    resolved = ensure_file_exists(path)
    if not resolved.is_dir():
        raise SourceValidationError("Source path is not a directory", path=str(resolved))
    return resolved


def ensure_regular_file(path: Path) -> Path:
    """Resolve ``path`` and raise unless it points to a regular file."""
    resolved = ensure_file_exists(path)
    if not resolved.is_file():
        raise SourceValidationError("Source path is not a file", path=str(resolved))
    return resolved
