"""Session-scoped, loopback-only, opaque artifact delivery (never a directory server)."""

import hashlib
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .core import artifact, contained, project_lock, read


class MediaServer:
    def __init__(self, root):
        self.root = root
        self.registry = {}
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass  # Do not leak capability URLs or write protocol stdout.

            def do_HEAD(self):
                self.deliver(False)

            def do_GET(self):
                self.deliver(True)

            def deliver(self, body):
                if self.headers.get("Host") != owner.origin.removeprefix("http://"):
                    self.send_error(403)
                    return
                record = owner.registry.get(self.path)
                if record is None:
                    self.send_error(404)
                    return
                try:
                    with project_lock(owner.root):
                        item = artifact(owner.root, read(owner.root), *record)
                        media = open(contained(owner.root, item["path"]), "rb")
                    with media:
                        h = hashlib.sha256()
                        for chunk in iter(lambda: media.read(1024 * 1024), b""):
                            h.update(chunk)
                        if h.hexdigest() != record[1]:
                            raise ValueError("Changed media")
                        size = media.tell()
                        start, end, status = 0, size - 1, 200
                        value = self.headers.get("Range")
                        if value:
                            match = re.fullmatch(r"bytes=(\d*)-(\d*)", value)
                            try:
                                if not match or not any(match.groups()):
                                    raise ValueError()
                                a, b = match.groups()
                                if not a:
                                    length = int(b)
                                    if length <= 0:
                                        raise ValueError()
                                    start = max(0, size - length)
                                else:
                                    start = int(a)
                                    end = min(int(b), size - 1) if b else size - 1
                                if start > end or start >= size:
                                    raise ValueError()
                            except ValueError:
                                self.send_response(416)
                                self.send_header("Content-Range", f"bytes */{size}")
                                self.end_headers()
                                return
                            status = 206
                        self.send_response(status)
                        self.send_header("Content-Type", "video/mp4")
                        self.send_header("Accept-Ranges", "bytes")
                        self.send_header("Content-Length", str(end - start + 1))
                        self.send_header("Cache-Control", "no-store")
                        self.send_header("X-Content-Type-Options", "nosniff")
                        if status == 206:
                            self.send_header(
                                "Content-Range", f"bytes {start}-{end}/{size}"
                            )
                        self.end_headers()
                        if body:
                            media.seek(start)
                            remaining = end - start + 1
                            while remaining:
                                chunk = media.read(min(65536, remaining))
                                if not chunk:
                                    break
                                self.wfile.write(chunk)
                                remaining -= len(chunk)
                except (OSError, ValueError, KeyError):
                    # A failed current-byte validation never serves the stale media.
                    self.send_error(409, "Artifact unavailable or changed")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.origin = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def register(self, item):
        record = (item["id"], item["sha256"])
        for path, existing in self.registry.items():
            if existing == record:
                return self.origin + path
        path = "/" + secrets.token_urlsafe(32)
        self.registry[path] = record
        return self.origin + path

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.registry.clear()
