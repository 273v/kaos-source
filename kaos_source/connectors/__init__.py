"""Transport connectors — :class:`SourceConnector` implementations for
URI-addressable resources (filesystem, archive, http, browser, memory).

Auto-registers all 5 transport connectors into
:data:`kaos_source.registry.connector_registry.default_connector_registry`
on import (Track 1 chunk 4). :class:`SourceService` consumes that
registry instead of hardcoding the connector list.

Out-of-tree custom transport connectors register explicitly::

    from kaos_source.registry import default_connector_registry
    default_connector_registry.register(MyCustomConnector(), force=True)
"""

from kaos_source.connectors.archive import ArchiveConnector
from kaos_source.connectors.base import SourceConnector
from kaos_source.connectors.browser import BrowserConnector
from kaos_source.connectors.filesystem import FilesystemConnector
from kaos_source.connectors.http import HttpConnector
from kaos_source.connectors.memory import MemoryConnector
from kaos_source.registry.connector_registry import default_connector_registry

# Auto-register the 5 built-in transport connector CLASSES (not
# instances) so each :class:`SourceService` constructs fresh instances
# — preserves the pre-chunk-4 contract that MemoryConnector state does
# not leak across services. ``force=True`` makes module re-imports
# idempotent (e.g. during pytest collection with multiple test sessions).
default_connector_registry.register(FilesystemConnector, force=True)
default_connector_registry.register(ArchiveConnector, force=True)
default_connector_registry.register(MemoryConnector, force=True)
default_connector_registry.register(HttpConnector, force=True)
default_connector_registry.register(BrowserConnector, force=True)


__all__ = [
    "ArchiveConnector",
    "BrowserConnector",
    "FilesystemConnector",
    "HttpConnector",
    "MemoryConnector",
    "SourceConnector",
]
