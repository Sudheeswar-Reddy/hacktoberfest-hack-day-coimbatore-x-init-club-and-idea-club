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
    """Which capture DB to compile. $AFRAMES_DB if set; otherwise the most recently
    written of: data/capture.sqlite (extensions), the OS recorder's DB, and nocta's
    DB (`aframes record` on macOS)."""
    from activity_frames import RecorderDBNotFound

    if config.AFRAMES_DB_EXPLICIT:
        if not Path(config.AFRAMES_DB).exists():
            raise RecorderDBNotFound(
                f"No capture data yet at {config.AFRAMES_DB}. Start the engine "
                "(`python -m stuckpoint serve`) and browse with the extension, or run "
                "`python -m stuckpoint record`.")
        return config.AFRAMES_DB
    from activity_frames import find_default_db

    candidates = [Path(config.AFRAMES_DB), Path(config.RECORDER_DB)]
    try:
        candidates.append(Path(find_default_db()))
    except RecorderDBNotFound:
        pass
    existing = [p for p in candidates if p.exists()]
    if not existing:
        raise RecorderDBNotFound(
            "No capture data yet. Start the engine (`python -m stuckpoint serve`) and browse "
            "with the Chrome/VS Code extension, or run `python -m stuckpoint record`, "
            "or set STUCKPOINT_SOURCE=fixture.")
    return str(max(existing, key=lambda p: p.stat().st_mtime))


def report_frames(days: int | None = None) -> list[dict]:
    """Frames for the skills report, over several local days. Each frame gets
    `_day` and a date-qualified `id` ("2026-10-08/f-0007"), so ids never clash."""
    if config.SOURCE == "fixture":
        doc = _load_fixture(config.FIXTURE)
        day = doc.get("window", {}).get("day") or datetime.now().strftime("%Y-%m-%d")
        return [{**f, "_day": day, "id": f"{day}/{f['id']}"} for f in doc["frames"]]

    from datetime import timedelta

    from activity_frames import ActivityLog

    log = ActivityLog(capture_db(), min_minutes=0)
    out: list[dict] = []
    try:
        today = datetime.now().date()
        for back in range((days or config.REPORT_DAYS) - 1, -1, -1):
            day = (today - timedelta(days=back)).isoformat()
            for f in log.day(day).to_dict()["frames"]:
                out.append({**f, "_day": day, "id": f"{day}/{f['id']}"})
    finally:
        log.close()
    return out


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
