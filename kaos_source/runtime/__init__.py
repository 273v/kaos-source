"""Runtime — execution machinery for kaos-source.

Mirrors :mod:`kaos_agents.runtime` (Track 2 chunk 2). Holds free-function
helpers and concrete execution classes that the ABCs in
:mod:`kaos_source.base` and the connectors in :mod:`kaos_source.connectors`
compose. Each module here does ONE thing — keeping the contracts layer
slim and the connector implementations free of boilerplate.

Modules (added in chunk 2):

- :mod:`.time`             — ``now_iso``, ``timestamp_to_iso``
- :mod:`.mime`             — ``guess_mime_type``
- :mod:`.cursor`           — ``encode_cursor``, ``decode_cursor`` (opaque
                             pagination cursors)
- :mod:`.policy`           — ``assert_roots_allow_path`` /
                             ``assert_roots_allow_uri`` /
                             ``path_matches_patterns`` /
                             ``ensure_file_exists`` /
                             ``ensure_directory`` / ``ensure_regular_file``
- :mod:`.preview_decode`   — ``decode_preview_payload`` (binary vs text
                             auto-detection for SourcePreview)
- :mod:`.materialization`  — ``materialize_local_path`` /
                             ``materialize_stream`` / ``materialize_bytes``
                             plus ``default_target_path``,
                             ``copy_path_to_disk``, ``copy_stream_to_disk``,
                             ``read_stream_bytes``
- :mod:`.service`          — :class:`SourceService` (router + job queue)

Dependency direction: ``runtime/`` may import from :mod:`kaos_source.base`,
:mod:`kaos_source.errors`, :mod:`kaos_source.models`, and
:mod:`kaos_source.options`. It MUST NOT import from
:mod:`kaos_source.connectors`, :mod:`kaos_source.apis`, or
:mod:`kaos_source.parsers` — those compose runtime helpers, not the
other way around.
"""

from __future__ import annotations

# Note: SourceService is *not* eagerly re-exported here — runtime/service.py
# depends on connectors/, which depends on runtime/cursor + runtime/policy
# + runtime/materialization, which would re-enter this package on its first
# import and circle back through service. Callers should import the service
# explicitly:
#
#     from kaos_source.runtime.service import SourceService
#
# (or via the back-compat shim ``from kaos_source.service import SourceService``).

__all__: list[str] = []
