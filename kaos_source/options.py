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

    # KSRC-03: archive bomb caps. Both apply to ZIP/TAR iteration in
    # ``ArchiveConnector._iter_members``.
    #
    # ``max_total_uncompressed`` — sum of all member uncompressed sizes
    # the connector will surface in one ``discover`` call. The default
    # 10 GiB is large enough for legitimate document-bundle archives but
    # tight enough to catch quadratic-blowup ZIPs (a 50 GB bomb expands
    # to TB during iteration).
    #
    # ``max_decompression_ratio`` — for ZIP archives, if any member's
    # ``uncompressed_size / compressed_size`` exceeds this ratio, the
    # connector raises ``SourceValidationError``. The 100:1 default
    # passes legitimate text/JSON archives (typical ratios 5-30:1) and
    # blocks the well-known billion-zero / billion-laughs zip patterns.
    # Set to 0 to disable.
    max_total_uncompressed: int = Field(default=10 * 1024 * 1024 * 1024, ge=0)
    max_decompression_ratio: float = Field(default=100.0, ge=0.0)

    # KSRC-06: archive symlink handling. When False (default), TAR
    # members that are symlinks or hardlinks are skipped entirely —
    # blocks the ``../../etc/passwd``-shaped archive escape. ZIPs do not
    # encode symlinks at the format level (always file or directory).
    allow_symlinks: bool = False


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
