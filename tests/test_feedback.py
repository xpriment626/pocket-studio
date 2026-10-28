import json
import subprocess
import sys
import unittest
from unittest.mock import patch
from concurrent.futures import ProcessPoolExecutor

from support import entry, fixture

from pocket_studio.core import read, submit_feedback


def write_feedback(root, item, i):
    return submit_feedback(root, entry(item, str(i)))


class Feedback(unittest.TestCase):
    def setUp(self):
        self.tmp, self.root, self.item = fixture()
        self.addCleanup(self.tmp.cleanup)

    def test_validation_and_version_binding(self):
        for change in [
            dict(sha256="stale"),
            dict(sha256=None),
            dict(request_id=""),
            dict(id="missing"),
            dict(time=-1),
            dict(time=3),
            dict(time=float("nan")),
            dict(time=float("inf")),
            dict(time=True),
            dict(author="agent"),
        ]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                submit_feedback(self.root, entry(self.item, **change))
        submit_feedback(self.root, entry(self.item, decision="approve"))
        self.assertEqual(read(self.root)["renders"][1]["creative_status"], "unreviewed")
        (self.root / "video.mp4").write_bytes(b"changed")
        with self.assertRaises(ValueError):
            submit_feedback(self.root, entry(self.item))

    def test_retry_conflict_and_history(self):
        (self.root / "reviews").mkdir()
        old = self.root / "reviews/old.json"
        old.write_text('{"author":"human"}')
        first = submit_feedback(self.root, entry(self.item))
        again = submit_feedback(self.root, entry(self.item))
        self.assertTrue(again["duplicate"])
        self.assertEqual(first["id"], again["id"])
        with self.assertRaises(ValueError):
            submit_feedback(self.root, entry(self.item, note="different"))
        submit_feedback(self.root, entry(self.item, "second", decision="approve"))
        replay = submit_feedback(self.root, entry(self.item))
        self.assertEqual(replay["current_status"], "approved")
        self.assertEqual(len(read(self.root)["feedback_history"]), 2)
        self.assertEqual(json.loads(old.read_text()), {"author": "human"})

    def test_concurrent_processes_and_cli_writer(self):
        source = self.root / "reference.txt"
        source.write_text("data only")
        command = [
            sys.executable,
            "-m",
            "pocket_studio.cli",
            "source",
            "add",
            str(source),
            "--project",
            str(self.root),
        ]
        with ProcessPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(write_feedback, self.root, self.item, i) for i in range(12)
            ]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for f in futures:
                f.result()
        self.assertEqual(len(read(self.root)["feedback_history"]), 12)
        self.assertEqual(len(read(self.root)["sources"]), 1)
        with ProcessPoolExecutor(max_workers=4) as pool:
            results = [
                f.result()
                for f in [
                    pool.submit(write_feedback, self.root, self.item, 99)
                    for _ in range(8)
                ]
            ]
        self.assertEqual(len({r["id"] for r in results}), 1)

    def test_failed_save_does_not_acknowledge_or_change_state(self):
        before = (self.root / "motion.json").read_bytes()
        with patch("pocket_studio.core.os.replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                submit_feedback(self.root, entry(self.item, decision="approve"))
        self.assertEqual((self.root / "motion.json").read_bytes(), before)
        self.assertEqual(list(self.root.glob("tmp*")), [])

    def test_direct_cli_note_file_and_file_import(self):
        note = self.root / "note.txt"
        note.write_text("Actual user note\nwith newline")
        cmd = [
            sys.executable,
            "-m",
            "pocket_studio.cli",
            "feedback",
            "--project",
            str(self.root),
            "--id",
            self.item["id"],
            "--sha256",
            self.item["sha256"],
            "--decision",
            "revise",
            "--time",
            "0.25",
            "--note-file",
            str(note),
            "--request-id",
            "direct",
        ]
        p = subprocess.run(cmd, text=True, capture_output=True, cwd="/tmp")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(
            read(self.root)["feedback_history"][0]["payload"]["note"], note.read_text()
        )
        payload = self.root / "feedback.json"
        payload.write_text(json.dumps(entry(self.item, "import")))
        p = subprocess.run(
            [
                sys.executable,
                "-m",
                "pocket_studio.cli",
                "feedback",
                "--project",
                str(self.root),
                "--file",
                str(payload),
            ],
            capture_output=True,
        )
        self.assertEqual(p.returncode, 0)
