import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from saturnino.downloader import download_candidate, safe_filename
from saturnino.models import MediaCandidate


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b"synthetic media bytes"
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        return


def test_safe_filename_is_stable_and_removes_path_characters() -> None:
    assert safe_filename("Chainsmoker Cat", "1", "mp4") == "Chainsmoker Cat - 01.mp4"
    assert safe_filename("A/B: C?", "special", "mkv") == "A_B_ C_ - special.mkv"


def test_download_candidate_streams_direct_file(tmp_path: Path) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        candidate = MediaCandidate(f"http://127.0.0.1:{server.server_port}/video.mp4", "mp4", 100)
        updates: list[tuple[int, int | None]] = []
        path = asyncio.run(
            download_candidate(
                candidate,
                "Example",
                "1",
                tmp_path,
                lambda written, total: updates.append((written, total)),
            )
        )
        assert path.read_bytes() == b"synthetic media bytes"
        assert updates == [(len(b"synthetic media bytes"), len(b"synthetic media bytes"))]
    finally:
        server.shutdown()
        thread.join()
