import http.client
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from support import fixture

from pocket_studio.media import MediaServer


class Media(unittest.TestCase):
    def setUp(self):
        self.tmp, self.root, self.item = fixture()
        self.addCleanup(self.tmp.cleanup)
        self.server = MediaServer(self.root)
        self.addCleanup(self.server.close)
        self.url = self.server.register(self.item)

    def test_ranges_boundaries_stale_and_head(self):
        raw = (self.root / "video.mp4").read_bytes()
        for value, expected in [
            ("bytes=0-99", raw[:100]),
            ("bytes=100-", raw[100:]),
            ("bytes=-40", raw[-40:]),
        ]:
            with urlopen(Request(self.url, headers={"Range": value})) as response:
                self.assertEqual(response.status, 206)
                self.assertEqual(response.read(), expected)
        with urlopen(Request(self.url, method="HEAD")) as response:
            self.assertEqual(int(response.headers["Content-Length"]), len(raw))
            self.assertEqual(response.read(), b"")
        for value in [
            "bytes=99999999-",
            "bytes=4-2",
            "bytes=0-1,3-4",
            "bytes=-0",
            "bad",
        ]:
            with self.assertRaises(HTTPError) as e:
                urlopen(Request(self.url, headers={"Range": value}))
            self.assertEqual(e.exception.code, 416)
        for path in [
            "/video.mp4",
            "/motion.json",
            "/../motion.json",
            "/%2e%2e/motion.json",
            self.url[len(self.server.origin) :] + "?x=1",
        ]:
            with self.assertRaises(HTTPError) as e:
                urlopen(self.server.origin + path)
            self.assertEqual(e.exception.code, 404)
        with self.assertRaises(HTTPError) as e:
            urlopen(Request(self.url, headers={"Host": "attacker.example"}))
        self.assertEqual(e.exception.code, 403)
        (self.root / "video.mp4").write_bytes(b"stale")
        with self.assertRaises(HTTPError) as e:
            urlopen(self.url)
        self.assertEqual(e.exception.code, 409)

    def test_symlink_escape_and_cleanup(self):
        (self.root / "video.mp4").unlink()
        (self.root / "video.mp4").symlink_to("/etc/hosts")
        with self.assertRaises(HTTPError) as e:
            urlopen(self.url)
        self.assertEqual(e.exception.code, 409)
        other = MediaServer(self.root)
        port = other.server.server_port
        other.close()
        self.assertFalse(other.thread.is_alive())
        self.assertFalse(other.registry)
        with self.assertRaises(OSError):
            http.client.HTTPConnection("127.0.0.1", port, timeout=1).request("GET", "/")
