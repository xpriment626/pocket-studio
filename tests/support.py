import subprocess
import tempfile
from pathlib import Path

from pocket_studio.core import digest, save


def fixture():
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    path = root / "video.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000",
            "-t",
            "2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(path),
        ],
        check=True,
    )
    item = dict(
        id="render-a",
        label="A",
        path="video.mp4",
        sha256=digest(path),
        duration=2,
        creative_status="unreviewed",
    )
    other = dict(item, id="render-b", label="B")
    save(
        root / "motion.json",
        dict(
            schema_version=1,
            title="Synthetic test",
            sources=[],
            renders=[item, other],
            cuts=[],
        ),
    )
    return tmp, root, item


def entry(item, request="test", **changes):
    return dict(
        dict(
            id=item["id"],
            sha256=item["sha256"],
            decision="revise",
            time=0.5,
            note="Synthetic note",
            author="human",
            request_id=request,
        ),
        **changes,
    )
