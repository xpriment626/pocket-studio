"""Shared local project operations; no optional dependencies or protocol IO."""

import hashlib
import json
import math
import os
import subprocess
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as f:
            temporary = f.name
            json.dump(data, f, indent=2, allow_nan=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def run(argv, cwd=None):
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        raise ValueError(f"{Path(argv[0]).name} failed: {result.stderr[-2000:]}")
    return result.stdout


def probe(path):
    return json.loads(
        run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(path),
            ]
        )
    )


def media_duration(info):
    value = float(info.get("format", {}).get("duration", 0))
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Media requires a positive finite duration")
    return value


def root_at(value):
    root = Path(value).resolve()
    if not contained(root, "motion.json").is_file():
        raise ValueError(f"No motion.json in {root}")
    return root


def read(root):
    return json.loads(contained(root, "motion.json").read_text())


def contained(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Project paths must stay inside the project")
    return path


def new_id(prefix):
    return prefix + "-" + uuid.uuid4().hex[:12]


@contextmanager
def project_lock(root):
    """Serialize cooperating writers on local filesystems (macOS/Linux)."""
    import fcntl

    with open(contained(root, ".motion.lock"), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def artifact(root, data, artifact_id, expected_hash=None):
    item = next(
        (x for x in data["renders"] + data["cuts"] if x["id"] == artifact_id), None
    )
    if not item or (expected_hash is not None and expected_hash != item["sha256"]):
        raise ValueError("Artifact missing or stale hash; review the current version")
    path = contained(root, item["path"])
    if digest(path) != item["sha256"]:
        raise ValueError("Artifact bytes changed; register and review a new version")
    return item


def inspect_project(root):
    with project_lock(root):
        data = read(root)
        for item in data["renders"] + data["cuts"]:
            artifact(root, data, item["id"])
        return data


def review_versions(root, ids):
    if not isinstance(ids, list) or not 1 <= len(ids) <= 2 or len(set(ids)) != len(ids):
        raise ValueError("Select one or two distinct artifact IDs")
    with project_lock(root):
        data = read(root)
        versions = []
        for artifact_id in ids:
            item = artifact(root, data, artifact_id)
            versions.append(dict(item, file_uri=contained(root, item["path"]).as_uri()))
        return versions


def submit_feedback(root, entry):
    """Persist the decision and retry record together in one atomic manifest write.

    Existing reviews/*.json remain intact. New history lives in motion.json to
    avoid a two-file transaction that could acknowledge an uncommitted decision.
    """
    if not isinstance(entry, dict):
        raise ValueError("Feedback must be an object")
    if not isinstance(entry.get("sha256"), str) or not entry["sha256"]:
        raise ValueError("Feedback requires the expected artifact hash")
    with project_lock(root):
        data = read(root)
        item = artifact(root, data, entry.get("id"), entry["sha256"])
        if (
            entry.get("decision") not in ("approve", "revise")
            or entry.get("author") != "human"
        ):
            raise ValueError(
                "Feedback requires human attribution and approve/revise decision"
            )
        t = entry.get("time", 0)
        if (
            isinstance(t, bool)
            or not isinstance(t, (float, int))
            or not math.isfinite(t)
            or not 0 <= t <= item["duration"]
        ):
            raise ValueError("Feedback timestamp is outside the artifact")
        note = entry.get("note", "")
        if not isinstance(note, str) or len(note) > 100000:
            raise ValueError("Note must be text of at most 100000 characters")
        request_id = entry.get("request_id")
        if request_id is None:
            request_id = new_id("request")
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 200:
            raise ValueError("Request ID must be text of 1..200 characters")
        payload = dict(
            id=item["id"],
            sha256=item["sha256"],
            author="human",
            decision=entry["decision"],
            time=t,
            note=note,
        )
        history = data.setdefault("feedback_history", [])
        for old in history:
            if old["request_id"] == request_id:
                if old["payload"] != payload:
                    raise ValueError("Request ID already used with different feedback")
                return dict(
                    old["result"],
                    current_status=item["creative_status"],
                    duplicate=True,
                )
        fid = new_id("feedback")
        item["creative_status"] = (
            "approved" if payload["decision"] == "approve" else "revision_requested"
        )
        item["feedback"] = fid
        result = dict(
            id=fid,
            artifact=item["id"],
            sha256=item["sha256"],
            status=item["creative_status"],
            request_id=request_id,
            recorded_at=now(),
            attribution="caller supplied; not identity verification",
        )
        history.append(dict(request_id=request_id, payload=payload, result=result))
        save(contained(root, "motion.json"), data)
        return dict(result, current_status=item["creative_status"], duplicate=False)
