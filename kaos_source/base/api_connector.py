"""ApiConnector — ABC for httpx-backed REST API connectors.

Today's FR/eCFR/EDGAR/GovInfo/GLEIF "connectors" live in
:mod:`kaos_source.connectors` but do *not* subclass
:class:`SourceConnector` — they're free-function modules with embedded
settings classes, called from sibling ``tools_*.py`` files at the
package root. Chunk 5 of this refactor (Track 1) reorganizes them into
:mod:`kaos_source.apis` subpackages, each implementing this ABC.

Why a separate ABC from :class:`SourceConnector`:

- :class:`SourceConnector` is shaped around URI-addressable resources
  (filesystem paths, HTTP URLs, archive members) where every connector
  implements describe/discover/preview/materialize in the same way.
- API connectors are shaped around *queries* (search by keyword) and
  *identifiers* (get by accession number, document number, LEI). Each
  API has its own idiomatic search/get parameters — forcing a single
  signature would either lose typing or pollute every method with a
  generic ``**kwargs``.

The contract here is intentionally minimal: every subclass exposes
:meth:`metadata` as a classmethod, declaring which capabilities it
supports via :attr:`ApiMetadata.capabilities`. The capability methods
themselves (``search``, ``get``, ``preview``, ``materialize``) are
satisfied structurally — see :mod:`kaos_source.base.protocols` for the
:class:`SupportsSearch` / :class:`SupportsGet` / :class:`SupportsPreview`
/ :class:`SupportsMaterialize` Protocols.

Type discipline (mirrors :class:`kaos_agents.base.agent.KaosAgent`):

- :class:`ApiConnector` is a plain Python ABC (connectors have
  *behavior*; only value types are pydantic).
- :meth:`ApiConnector.metadata` is a classmethod returning a frozen
  pydantic :class:`ApiMetadata`. The default builds from kebab-cased
  class name + first ``__doc__`` line; subclasses override to set
  ``base_url``, ``requires_auth``, ``capabilities``, etc.
"""

from __future__ import annotations

import re
from abc import ABC

from kaos_source.base.metadata import ApiMetadata

_CAMEL_TO_UNDERSCORE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _default_api_name(cls: type) -> str:
    """Snake-cased class name as the default api discriminator.

    ``FederalRegisterApiConnector`` -> ``federal_register_api_connector``;
    ``EdgarApiConnector`` -> ``edgar_api_connector``. Strips leading
    underscores so private/test subclasses still produce a valid
    :attr:`ApiMetadata.name`.
    """
    name = cls.__name__.lstrip("_")
    return _CAMEL_TO_UNDERSCORE.sub("_", name).lower() if name else "api"


def _first_doc_line(cls: type) -> str:
    """First non-empty line of a class's docstring, or fallback."""
    doc = cls.__doc__ or ""
    for line in doc.strip().splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return "(no description)"


class ApiConnector(ABC):  # noqa: B024 — capability methods are structural (see Protocols)
    """ABC for an httpx-backed REST API connector.

    Subclasses implement the capability methods declared in
    :attr:`metadata().capabilities` — ``search()``, ``get()``,
    ``preview()``, ``materialize()`` — with API-specific signatures.
    Consumers route via :class:`ApiRegistry` (chunk 4) keyed by
    ``metadata().name``.

    The default :meth:`metadata` builds an :class:`ApiMetadata` from the
    class name + first line of ``__doc__``. Override for richer
    identity (set ``base_url``, ``requires_auth``, ``capabilities``).
    """

    @classmethod
    def metadata(cls) -> ApiMetadata:
        """Frozen identity record for this api connector class.

        Subclasses override to set ``base_url``, ``requires_auth``,
        ``capabilities``, ``tags``. Default builds from snake-cased
        class name + ``__doc__``.
        """
        return ApiMetadata(
            name=_default_api_name(cls),
            description=_first_doc_line(cls),
        )


__all__ = ["ApiConnector"]
