"""Activity source (Person 1): live Activity Frames capture, or the fixture file.

Both paths return the same thing: a list of Activity Frames frame dicts
(schema v1, see instructions.md Part 3.1).
"""
from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from .. import config


@lru_cache(maxsize=1)
def _load_fixture(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def capture_db() -> str:
    """Which capture DB to compile: $AFRAMES_DB, else the most recently written of
    nocta's DB (`aframes record`, macOS) and our recorder's DB (any OS)."""
    if config.AFRAMES_DB:
        return config.AFRAMES_DB
    from activity_frames import RecorderDBNotFound, find_default_db

    candidates = [Path(config.RECORDER_DB)]
    try:
        candidates.append(Path(find_default_db()))
    except RecorderDBNotFound:
        pass
    existing = [p for p in candidates if p.exists()]
    if not existing:
        raise RecorderDBNotFound(
            "No capture database yet. Start capture with `python -m stuckpoint record` "
            "(or `aframes record` on macOS), or set STUCKPOINT_SOURCE=fixture.")
    return str(max(existing, key=lambda p: p.stat().st_mtime))


def get_frames(minutes: int = 60) -> list[dict]:
    """Frames for the last `minutes` (live) or the whole fixture (fixture mode)."""
    if config.SOURCE == "fixture":
        return list(_load_fixture(config.FIXTURE)["frames"])

    from activity_frames import ActivityLog

    # min_minutes=0: keep short frames — quick trips to Stack Overflow/ChatGPT
    # are exactly the loop signal we need (the library default 0.5 drops them).
    log = ActivityLog(capture_db(), min_minutes=0)
    try:
        return log.recent(hours=minutes / 60).to_dict()["frames"]
    finally:
        log.close()


def now() -> datetime:
    """'Current time' for detection. In fixture mode: the end of the last frame,
    so the fixture always looks like it is happening right now."""
    if config.SOURCE == "fixture":
        doc = _load_fixture(config.FIXTURE)
        day = doc.get("window", {}).get("day") or datetime.now().strftime("%Y-%m-%d")
        frames = doc.get("frames") or []
        last_end = max((f["end"] for f in frames), default="23:59:59")
        return datetime.strptime(f"{day} {last_end}", "%Y-%m-%d %H:%M:%S")
    return datetime.now().replace(microsecond=0)
