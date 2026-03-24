from __future__ import annotations

import base64
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

from kaos_core import ArtifactManifest, ArtifactRef, ArtifactRetentionPolicy
from kaos_core.types.content import KaosModel
from pydantic import Field

from kaos_source.errors import SourceErrorInfo, SourceValidationError


class SourceKind(StrEnum):
    FILESYSTEM = "filesystem"
    ARCHIVE = "archive"
    MEMORY = "memory"
    HTTP = "http"
    BROWSER = "browser"
    SEARCH = "search"


class SourceOperation(StrEnum):
    DESCRIBE = "describe"
    DISCOVER = "discover"
    PREVIEW = "preview"
    MATERIALIZE = "materialize"


class SourceJobStatus(StrEnum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SourceLocator(KaosModel):
    source_kind: SourceKind
    uri: str
    path: str | None = None
    archive_path: str | None = None
    member_path: str | None = None
    name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def filesystem(cls, path: str | Path) -> SourceLocator:
        resolved = Path(path).expanduser()
        if not resolved.is_absolute():
            resolved = (Path.cwd() / resolved).resolve()
        else:
            resolved = resolved.resolve()
        return cls(
            source_kind=SourceKind.FILESYSTEM,
            uri=resolved.as_uri(),
            path=str(resolved),
        )

    @classmethod
    def archive(cls, path: str | Path) -> SourceLocator:
        filesystem_locator = cls.filesystem(path)
        return cls(
            source_kind=SourceKind.ARCHIVE,
            uri=f"archive+{filesystem_locator.uri}",
            archive_path=filesystem_locator.path,
            path=filesystem_locator.path,
        )

    @classmethod
    def archive_member(cls, archive_path: str | Path, member_path: str) -> SourceLocator:
        archive_locator = cls.archive(archive_path)
        normalized_member = _normalize_archive_member_path(member_path)
        return cls(
            source_kind=SourceKind.ARCHIVE,
            uri=f"{archive_locator.uri}#{quote(normalized_member)}",
            archive_path=archive_locator.archive_path,
            path=archive_locator.path,
            member_path=normalized_member,
            name=PurePosixPath(normalized_member).name,
        )

    @classmethod
    def memory(cls, name: str | None = None) -> SourceLocator:
        suffix = quote(name) if name is not None else ""
        uri = "memory://"
        if suffix:
            uri = f"memory://{suffix}"
        return cls(
            source_kind=SourceKind.MEMORY,
            uri=uri,
            name=name,
        )

    @classmethod
    def http(cls, url: str) -> SourceLocator:
        normalized_url = _normalize_http_url(url)
        parsed = urlsplit(normalized_url)
        name = PurePosixPath(parsed.path).name or parsed.netloc
        return cls(
            source_kind=SourceKind.HTTP,
            uri=normalized_url,
            name=name,
        )

    @classmethod
    def browser(cls, url: str) -> SourceLocator:
        normalized_url = _normalize_http_url(url)
        parsed = urlsplit(normalized_url)
        name = PurePosixPath(parsed.path).name or parsed.netloc
        return cls(
            source_kind=SourceKind.BROWSER,
            uri=normalized_url,
            name=name,
        )


class SourceProvenance(KaosModel):
    source_kind: SourceKind
    locator: SourceLocator
    connector_name: str
    retrieved_at: str
    request_metadata: dict[str, Any] = Field(default_factory=dict)
    parent_artifact_id: str | None = None


class SourceDescriptor(KaosModel):
    source_id: str
    source_kind: SourceKind
    locator: SourceLocator
    name: str
    mime_type: str | None = None
    size: int | None = None
    created_at: str | None = None
    modified_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: SourceProvenance
    can_materialize: bool = True
    preview_available: bool = True


class SourcePreview(KaosModel):
    source_id: str
    text_preview: str | None = None
    binary_preview_base64: str | None = None
    truncated: bool = False
    size: int | None = None
    mime_type: str | None = None

    @classmethod
    def from_binary(
        cls,
        *,
        source_id: str,
        payload: bytes,
        truncated: bool,
        size: int | None,
        mime_type: str | None,
    ) -> SourcePreview:
        return cls(
            source_id=source_id,
            binary_preview_base64=base64.b64encode(payload).decode("ascii"),
            truncated=truncated,
            size=size,
            mime_type=mime_type,
        )


class SourceMaterialization(KaosModel):
    descriptor: SourceDescriptor
    manifest: ArtifactManifest
    artifact_ref: ArtifactRef
    bytes_written: int
    retention_policy: ArtifactRetentionPolicy
    related_artifacts: list[ArtifactRef] = Field(default_factory=list)


class SourcePage(KaosModel):
    items: list[SourceDescriptor] = Field(default_factory=list)
    next_cursor: str | None = None
    total_count: int | None = None
    error_count: int = 0
    errors: list[SourceErrorInfo] = Field(default_factory=list)


class SourceJobResult(KaosModel):
    descriptor: SourceDescriptor | None = None
    page: SourcePage | None = None
    preview: SourcePreview | None = None
    materialization: SourceMaterialization | None = None


class SourceJob(KaosModel):
    job_id: str
    operation: SourceOperation
    status: SourceJobStatus
    submitted_at: str
    started_at: str | None = None
    finished_at: str | None = None
    progress_current: int = 0
    progress_total: int | None = None
    message: str | None = None
    locator: SourceLocator
    result: SourceJobResult | None = None
    error: SourceErrorInfo | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def _normalize_archive_member_path(member_path: str) -> str:
    normalized = PurePosixPath(member_path)
    if normalized.is_absolute():
        raise SourceValidationError("Archive member path must be relative", member_path=member_path)
    parts = normalized.parts
    if any(part == ".." for part in parts):
        raise SourceValidationError(
            "Archive member path cannot traverse upward",
            member_path=member_path,
        )
    return normalized.as_posix()


def _normalize_http_url(url: str) -> str:
    normalized = url.strip()
    parsed = urlsplit(normalized)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise SourceValidationError("HTTP source URL must use http or https", url=url)
    if not parsed.netloc:
        raise SourceValidationError("HTTP source URL must include a host", url=url)
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc, path, parsed.query, ""))
