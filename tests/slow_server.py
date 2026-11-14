"""Tiny throttled HTTP server with Range support, for manual and end-to-end tests.

Every path returns deterministic pseudo-random bytes derived from the path, so
/a/file.bin and /b/file.bin have the same name but different content.
Paths starting with /missing return 404.

Usage: python tests/slow_server.py [--port 8765] [--size 3000000] [--rate 100000]
"""

from __future__ import annotations

import argparse
import hashlib
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CHUNK = 8192


def content_for(path: str, size: int) -> bytes:
    """Deterministic content for a path (same path -> same bytes)."""
    out = bytearray()
    counter = 0
    while len(out) < size:
        out += hashlib.sha256(f"{path}:{counter}".encode()).digest()
        counter += 1
    return bytes(out[:size])


def make_handler(size: int, rate: int, ranges: bool = True):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # keep test output quiet
            pass

        def do_GET(self):
            if self.path.startswith("/missing"):
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = content_for(self.path, size)
            start = 0
            match = re.match(r"bytes=(\d+)-", self.headers.get("Range", ""))
            if match and ranges:
                start = int(match.group(1))
                if start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{size - 1}/{size}")
            else:
                self.send_response(200)
            if ranges:
                self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(size - start))
            self.end_headers()
            try:
                for pos in range(start, size, CHUNK):
                    self.wfile.write(body[pos : pos + CHUNK])
                    self.wfile.flush()
                    if rate:
                        time.sleep(CHUNK / rate)
            except (BrokenPipeError, ConnectionResetError):
                pass

    return Handler


def make_server(port: int = 0, size: int = 3_000_000, rate: int = 100_000, ranges: bool = True):
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(size, rate, ranges))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--size", type=int, default=3_000_000, help="bytes per file")
    parser.add_argument("--rate", type=int, default=100_000, help="bytes per second, 0 = unlimited")
    args = parser.parse_args()
    server = make_server(args.port, args.size, args.rate)
    print(f"serving on http://127.0.0.1:{args.port}  (size={args.size}, rate={args.rate}/s)")
    server.serve_forever()
