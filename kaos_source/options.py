from __future__ import annotations

from typing import Any

from kaos_core import ArtifactRetentionPolicy, ArtifactRole
from kaos_core.types.content import KaosModel
from pydantic import Field


class SourceDiscoverOptions(KaosModel):
    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=500)
    recursive: bool = True
    include_hidden: bool = False
    include_directories: bool = False
    max_depth: int | None = Field(default=None, ge=0)
    min_size: int | None = Field(default=None, ge=0)
    max_size: int | None = Field(default=None, ge=0)
    patterns: list[str] = Field(default_factory=list)


class SourcePreviewOptions(KaosModel):
    max_bytes: int = Field(default=1024, ge=1)
    encoding: str = "utf-8"


class SourceMaterializeOptions(KaosModel):
    artifact_name: str | None = None
    artifact_description: str | None = None
    target_path: str | None = None
    role: ArtifactRole = ArtifactRole.BODY
    retention_policy: ArtifactRetentionPolicy = ArtifactRetentionPolicy.SESSION
    metadata: dict[str, Any] = Field(default_factory=dict)
    checksum: bool = False
    ttl_seconds: int | None = Field(default=None, ge=1)
    workflow_id: str | None = None
