#!/usr/bin/env python3
"""Dev server for the playground: static files from ./dist with the right
mime types, no caching, and cross-origin isolation headers (COOP/COEP).

The playground itself does not need SharedArrayBuffer, but serving
cross-origin-isolated keeps it ready for pyodide.setInterruptBuffer (instant
Ctrl-C into runaway Python instead of a worker reboot) and mirrors what the
production host (BunnyCDN) is configured to send.

Usage: python3 serve.py [port]   (default 8343)
"""
import http.server
import os
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8343
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript",
        ".mjs": "text/javascript",
        ".wasm": "application/wasm",
        ".json": "application/json",
        ".zip": "application/zip",
        ".py": "text/x-python",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass  # quiet


if __name__ == "__main__":
    if not os.path.isdir(ROOT):
        sys.exit("dist/ not found — run ./build.sh first")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"serving {ROOT} at http://localhost:{PORT}/")
    server.serve_forever()
