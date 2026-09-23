import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from saturnino.models import MediaCandidate
from saturnino.validation import validate_candidate


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/ok.m3u8":
            body = b"#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:4,\nsegment.ts\n"
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.apple.mpegurl")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/html.m3u8":
            body = b"<html><body>#EXTM3U</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *_args: object) -> None:
        return


@pytest.fixture()
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join()


def test_validate_hls_bounds_to_a_manifest(server: str) -> None:
    candidate = MediaCandidate(url=f"{server}/ok.m3u8", media_type="hls", score=90)
    result = asyncio.run(validate_candidate(candidate, timeout=3))
    assert result.state == "valid"


def test_validate_rejects_html_masquerading_as_hls(server: str) -> None:
    candidate = MediaCandidate(url=f"{server}/html.m3u8", media_type="hls", score=90)
    result = asyncio.run(validate_candidate(candidate, timeout=3))
    assert result.state == "invalid"
