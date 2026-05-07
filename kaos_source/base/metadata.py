"""Frozen metadata records for kaos-source core concepts.

Mirrors :mod:`kaos_agents.types.metadata` and :mod:`kaos_core.types.metadata`.
Each concept's ABC carries a frozen pydantic :class:`KaosModel` describing
its identity (name, description, version, capabilities), returned via the
ABC's ``metadata()`` classmethod.

The three records:

- :class:`ConnectorMetadata` — :class:`SourceConnector` subclasses
- :class:`ApiMetadata` — :class:`ApiConnector` subclasses
- :class:`ParserMetadata` — :class:`SourceParser` subclasses

Naming
------

Names use the relaxed ``[a-z0-9][a-z0-9_.-]*`` pattern from kaos-agents
(connectors / apis / parsers are *internal* concepts — only MCP-exposed
:class:`ToolMetadata` enforces the strict ``kaos-{module}-{action}``
pattern). This lets us write ``federal_register``, ``edgar``,
``email.eml`` without forced segmentation.
"""

from __future__ import annotations

import re

from kaos_core.types.content import KaosModel
from pydantic import ConfigDict, Field, field_validator

from kaos_source.base.capabilities import SourceCapability
from kaos_source.models import SourceKind

_IDENT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.\-]*$")


class _BaseConceptMetadata(KaosModel):
    """Common fields shared by every kaos-source concept metadata.

    Subclasses add concept-specific fields. ``frozen=True`` makes
    instances safe to cache and use as dict keys.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True, frozen=True)

    name: str
    description: str
    module_name: str = "kaos_source"
    version: str = "1.0.0"
    capabilities: tuple[SourceCapability, ...] = Field(default_factory=tuple)
    tags: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        if not _IDENT_PATTERN.match(value):
            msg = (
                "metadata name must match [a-z0-9][a-z0-9_.-]*; "
                f"got {value!r}. Use lowercase letters, digits, '_', '.', or '-'."
            )
            raise ValueError(msg)
        return value


class ConnectorMetadata(_BaseConceptMetadata):
    """Describes a :class:`kaos_source.base.connector.SourceConnector` subclass.

    ``supported_kinds`` declares which :class:`SourceKind` URI schemes
    this connector handles — the :class:`ConnectorRegistry` (chunk 4)
    keys on these for routing.
    """

    supported_kinds: tuple[SourceKind, ...] = Field(default_factory=tuple)


class ApiMetadata(_BaseConceptMetadata):
    """Describes a :class:`kaos_source.base.api_connector.ApiConnector` subclass.

    ``base_url`` and ``requires_auth`` are advertised so consumers can
    pre-check connectivity / credentials without instantiating the
    connector.
    """

    base_url: str | None = None
    requires_auth: bool = False
    auth_env_var: str | None = Field(
        default=None,
        description=(
            "Primary env var that must be set when requires_auth=True "
            "(e.g. KAOS_SOURCE_GOVINFO_API_KEY)."
        ),
    )


class ParserMetadata(_BaseConceptMetadata):
    """Describes a :class:`kaos_source.base.parser.SourceParser` subclass.

    ``supported_mime_types`` and ``supported_extensions`` let the
    :class:`ParserRegistry` (chunk 4) route raw byte streams to the
    correct parser based on either MIME type or filename suffix.
    """

    supported_mime_types: tuple[str, ...] = Field(default_factory=tuple)
    supported_extensions: tuple[str, ...] = Field(default_factory=tuple)
