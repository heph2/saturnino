import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

pytest.importorskip("playwright")

from saturnino.browser import BrowserExtractor


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/episode":
            body = b'''<!doctype html><title>Fixture - Demo Episodio 1</title>
            <h1>Demo Episodio 1 Streaming</h1>
            <iframe title="Fixture player" src="/player"></iframe>'''
            self._send("text/html", body)
        elif self.path == "/player":
            body = b'''<!doctype html><button type="button" id="start">Play</button>
            <script>start.onclick = () => fetch('/stream/master.m3u8');</script>'''
            self._send("text/html", body)
        elif self.path == "/stream/master.m3u8":
            self._send("application/vnd.apple.mpegurl", b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1000\nvariant.m3u8\n")
        else:
            self.send_response(404)
            self.end_headers()

    def _send(self, content_type: str, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        return


@pytest.fixture()
def fixture_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/episode"
    finally:
        server.shutdown()
        thread.join()


def test_browser_captures_click_triggered_nested_frame_manifest(fixture_url: str) -> None:
    result = asyncio.run(BrowserExtractor(timeout=15).extract(fixture_url))
    assert result.selected is not None
    assert result.selected.media_type == "hls"
    assert result.selected.validation is not None
    assert result.selected.validation.state == "valid"
    assert result.provider == "127.0.0.1"
