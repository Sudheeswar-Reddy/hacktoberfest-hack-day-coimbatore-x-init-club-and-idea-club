"""Ingestion (Person 1): extension events -> capture DB in Activity Frames' schema.

The Chrome and VS Code extensions are our recorder on every OS. They POST
batches of events to /events; we write them into the tables the Activity
Frames compiler reads (`frames`, `ui_events`), so the unmodified library
compiles them into measured frames.

  focus  {"type":"focus","ts","app","title","url"}  -> one `frames` row (a heartbeat)
  input  {"type":"input","ts","app","keys","clicks"} -> one `text` ui_event whose
         text_content is 'x' * keys (Activity Frames counts len(text) as keystrokes,
         so the COUNT is exact while no typed text is ever stored) + one `click`
         row per click.
"""
from __future__ import annotations

import re
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from . import config
from .capture.recorder import open_db

MAX_KEYS_PER_EVENT = 5000       # a 10 s batch can't plausibly exceed this
MAX_CLICKS_PER_EVENT = 500
_SKIP_URL = re.compile(r"^(chrome|edge|brave|about|chrome-extension|devtools|view-source):", re.I)

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None
_conn_path: Optional[str] = None


def _db() -> sqlite3.Connection:
    global _conn, _conn_path
    if _conn is None or _conn_path != config.AFRAMES_DB:
        if _conn is not None:
            _conn.close()
        _conn, _conn_path = open_db(config.AFRAMES_DB), config.AFRAMES_DB
    return _conn


def to_capture_ts(ts: Any) -> Optional[str]:
    """'2026-10-08T07:43:10.123Z' -> '2026-10-08T07:43:10' (UTC, the format the compiler compares)."""
    if not isinstance(ts, str) or not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _count(v: Any, cap: int) -> int:
    try:
        return max(0, min(int(v), cap))
    except (TypeError, ValueError):
        return 0


def ingest(events: list[dict], source: str = "chrome") -> int:
    """Write events; returns how many were stored. Malformed events are skipped."""
    frames, ui = [], []
    default_app = "Code" if source == "vscode" else "Google Chrome"
    for e in events or []:
        if not isinstance(e, dict):
            continue
        ts = to_capture_ts(e.get("ts"))
        if not ts:
            continue
        app = str(e.get("app") or default_app)[:100]
        if e.get("type") == "focus":
            url = e.get("url") or None
            if url and _SKIP_URL.match(str(url)):
                continue                       # browser-internal pages are not activity
            title = (str(e.get("title") or "")[:300]) or None
            frames.append((ts, app, title, str(url)[:2000] if url else None, source[:20]))
        elif e.get("type") == "input":
            keys = _count(e.get("keys"), MAX_KEYS_PER_EVENT)
            clicks = _count(e.get("clicks"), MAX_CLICKS_PER_EVENT)
            if keys:
                ui.append((ts, "text", "x" * keys, app))
            ui.extend((ts, "click", None, app) for _ in range(clicks))
    if not frames and not ui:
        return 0
    with _lock:
        conn = _db()
        conn.executemany(
            "INSERT INTO frames (timestamp, app_name, window_name, focused, browser_url, url_source)"
            " VALUES (?,?,?,1,?,?)", frames)
        conn.executemany(
            "INSERT INTO ui_events (timestamp, event_type, text_content, app_name) VALUES (?,?,?,?)", ui)
        conn.commit()
    return len(frames) + len(ui)
