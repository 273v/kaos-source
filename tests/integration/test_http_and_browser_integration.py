from __future__ import annotations

import functools
import threading
from collections.abc import Generator
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from kaos_core import KaosContext, KaosRuntime
from kaos_core.protocol.roots import Root

from kaos_source import BrowserConnector, HttpConnector, SourceLocator, SourcePreviewOptions


def _context(runtime: KaosRuntime, *, roots: list[Root] | None = None) -> KaosContext:
    return KaosContext.create(session_id="source-integration", runtime=runtime, roots=roots)


@pytest.fixture()
def local_web_root(tmp_path: Path) -> Path:
    site = tmp_path / "site"
    site.mkdir()
    (site / "report.txt").write_text("live-http-body", encoding="utf-8")
    (site / "app.html").write_text(
        """
        <!doctype html>
        <html>
          <head>
            <meta charset="utf-8" />
            <title>Before Render</title>
            <script>
              window.addEventListener("load", () => {
                document.title = "After Render";
                document.getElementById("app").textContent = "Rendered from JS";
              });
            </script>
          </head>
          <body>
            <main id="app">Loading</main>
          </body>
        </html>
        """.strip(),
        encoding="utf-8",
    )
    return site


@pytest.fixture()
def local_http_server(local_web_root: Path) -> Generator[str]:
    handler = functools.partial(_QuietSimpleHTTPRequestHandler, directory=str(local_web_root))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    sockname = server.socket.getsockname()
    host = str(sockname[0])
    port = int(sockname[1])
    base_url = f"http://{host}:{port}"
    try:
        yield base_url
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


@pytest.mark.integration
async def test_http_connector_works_against_live_local_server(
    runtime: KaosRuntime,
    local_http_server: str,
) -> None:
    connector = HttpConnector()
    context = _context(runtime, roots=[Root(uri=f"{local_http_server}/", name="local-http")])
    locator = SourceLocator.http(f"{local_http_server}/report.txt")

    descriptor = await connector.describe(locator, context)
    preview = await connector.preview(locator, context, SourcePreviewOptions(max_bytes=4))
    materialization = await connector.materialize(locator, context)

    assert descriptor.size == len("live-http-body")
    assert preview.text_preview == "live"
    assert preview.truncated is True
    assert (
        await runtime.artifacts.read_text(materialization.manifest.artifact_id) == "live-http-body"
    )


@pytest.mark.integration
async def test_browser_connector_works_against_live_local_page(
    runtime: KaosRuntime,
    local_http_server: str,
) -> None:
    pytest.importorskip("playwright.async_api")

    connector = BrowserConnector(take_screenshot=True)
    context = _context(runtime, roots=[Root(uri=f"{local_http_server}/", name="local-http")])
    locator = SourceLocator.browser(f"{local_http_server}/app.html")

    descriptor = await connector.describe(locator, context)
    preview = await connector.preview(locator, context, SourcePreviewOptions(max_bytes=1024))
    materialization = await connector.materialize(locator, context)

    screenshot_ref = materialization.related_artifacts[0]
    rendered_html = await runtime.artifacts.read_text(materialization.manifest.artifact_id)
    screenshot_bytes = await runtime.artifacts.read_body(screenshot_ref.artifact_id)

    assert descriptor.metadata["title"] == "After Render"
    assert "Rendered from JS" in rendered_html
    assert "Rendered from JS" in (preview.text_preview or "")
    assert screenshot_ref.mime_type == "image/png"
    assert len(screenshot_bytes) > 0


class _QuietSimpleHTTPRequestHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        del format, args
