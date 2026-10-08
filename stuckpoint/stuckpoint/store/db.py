"""Local store (Person 1): signals, hints, solved marks, sessions, report claims.

SQLite in WAL mode, one short-lived connection per call, so the engine's HTTP
threads, its detection loop and the CLI can all use it at the same time.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from .. import config
from ..models import HintResponse, ReportClaim, SessionRecord, StuckSignal

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY, problem_key TEXT, status TEXT, created_at TEXT,
    updated_at TEXT, json TEXT);
CREATE INDEX IF NOT EXISTS idx_signals_key ON signals(problem_key, created_at);
CREATE TABLE IF NOT EXISTS hints (
    id TEXT PRIMARY KEY, signal_id TEXT, problem_key TEXT, level INTEGER,
    is_code INTEGER, blocked INTEGER, text TEXT, created_at TEXT, json TEXT);
CREATE INDEX IF NOT EXISTS idx_hints_key ON hints(problem_key, created_at);
CREATE TABLE IF NOT EXISTS marks (problem_key TEXT PRIMARY KEY, solved INTEGER, marked_at TEXT);
CREATE TABLE IF NOT EXISTS sessions (problem_key TEXT PRIMARY KEY, json TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS claims (id TEXT PRIMARY KEY, json TEXT, gate_status TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);
"""

ACTIVE = ("confirmed", "offered", "accepted")       # signals the UI should show
COUNTED = ("confirmed", "offered", "accepted", "dismissed", "snoozed")  # real stuck episodes


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | None = None):
        self.path = path or config.STUCKPOINT_DB
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(_SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path, timeout=10.0)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---- frames (latest snapshot, for debugging / the UI) ----------------
    def save_frames(self, frames: list[dict]) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO kv VALUES ('last_frames', ?, ?)",
                      (json.dumps(frames, ensure_ascii=False), _now()))

    def last_frames(self) -> list[dict]:
        with self._conn() as c:
            row = c.execute("SELECT value FROM kv WHERE key='last_frames'").fetchone()
        return json.loads(row[0]) if row else []

    # ---- signals ----------------------------------------------------------
    def save_signal(self, sig: StuckSignal) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO signals VALUES (?,?,?,?,?,?)",
                      (sig.id, sig.problem_key, sig.status, sig.created_at, _now(),
                       json.dumps(sig.to_dict())))

    def _signals(self, where: str = "", params: tuple = (), limit: int = 0) -> list[StuckSignal]:
        sql = f"SELECT json, status FROM signals {where} ORDER BY created_at DESC, rowid DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        with self._conn() as c:
            rows = c.execute(sql, params).fetchall()
        out = []
        for js, status in rows:
            sig = StuckSignal.from_dict(json.loads(js))
            sig.status = status                     # the column is authoritative
            out.append(sig)
        return out

    def get_signal(self, signal_id: str) -> Optional[StuckSignal]:
        rows = self._signals("WHERE id=?", (signal_id,), 1)
        return rows[0] if rows else None

    def last_signal_for(self, problem_key: str) -> Optional[StuckSignal]:
        rows = self._signals("WHERE problem_key=?", (problem_key,), 1)
        return rows[0] if rows else None

    def latest_signal(self, statuses: tuple = ACTIVE) -> Optional[StuckSignal]:
        marks = ",".join("?" * len(statuses))
        rows = self._signals(f"WHERE status IN ({marks})", tuple(statuses), 1)
        return rows[0] if rows else None

    def pending_signals(self) -> list[StuckSignal]:
        return self._signals("WHERE status IN ('confirmed','offered')")

    def signals_for(self, problem_key: str) -> list[StuckSignal]:
        return self._signals("WHERE problem_key=?", (problem_key,))

    def update_signal_status(self, signal_id: str, status: str) -> bool:
        sig = self.get_signal(signal_id)
        if sig is None:
            return False
        sig.status = status
        with self._conn() as c:
            c.execute("UPDATE signals SET status=?, updated_at=?, json=? WHERE id=?",
                      (status, _now(), json.dumps(sig.to_dict()), signal_id))
        return True

    # ---- hints ------------------------------------------------------------
    def save_hint(self, resp: HintResponse, problem_key: str) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO hints VALUES (?,?,?,?,?,?,?,?,?)",
                      (f"hint-{uuid.uuid4().hex[:8]}", resp.signal_id, problem_key, resp.level,
                       int(resp.is_code), int(resp.blocked), resp.text, _now(),
                       json.dumps(resp.to_dict())))

    def hints_for(self, problem_key: str, signal_id: str | None = None) -> list[HintResponse]:
        sql, params = "SELECT json FROM hints WHERE problem_key=?", [problem_key]
        if signal_id:
            sql += " AND signal_id=?"
            params.append(signal_id)
        with self._conn() as c:
            rows = c.execute(sql + " ORDER BY created_at, rowid", params).fetchall()
        return [HintResponse.from_dict(json.loads(r[0])) for r in rows]

    def hint_times(self, problem_key: str) -> list[str]:
        with self._conn() as c:
            return [r[0] for r in c.execute(
                "SELECT created_at FROM hints WHERE problem_key=? ORDER BY created_at", (problem_key,))]

    # ---- solved marks (set by the user, never guessed) --------------------
    def mark_solved(self, problem_key: str, solved: bool = True) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO marks VALUES (?,?,?)", (problem_key, int(solved), _now()))

    def is_solved(self, problem_key: str) -> Optional[bool]:
        with self._conn() as c:
            row = c.execute("SELECT solved FROM marks WHERE problem_key=?", (problem_key,)).fetchone()
        return None if row is None else bool(row[0])

    # ---- sessions + claims ------------------------------------------------
    def save_sessions(self, sessions: list[SessionRecord]) -> None:
        with self._conn() as c:
            c.executemany("INSERT OR REPLACE INTO sessions VALUES (?,?,?)",
                          [(s.problem_key, json.dumps(s.to_dict()), _now()) for s in sessions])

    def sessions(self) -> list[SessionRecord]:
        with self._conn() as c:
            rows = c.execute("SELECT json FROM sessions ORDER BY updated_at DESC").fetchall()
        return [SessionRecord.from_dict(json.loads(r[0])) for r in rows]

    def save_claims(self, claims: list[ReportClaim]) -> None:
        """Replace the stored report with the latest gated claims."""
        with self._conn() as c:
            c.execute("DELETE FROM claims")
            c.executemany("INSERT INTO claims VALUES (?,?,?,?)",
                          [(cl.id, json.dumps(cl.to_dict()), cl.gate_status, _now()) for cl in claims])

    def claims(self) -> list[ReportClaim]:
        with self._conn() as c:
            rows = c.execute("SELECT json FROM claims ORDER BY rowid").fetchall()
        return [ReportClaim.from_dict(json.loads(r[0])) for r in rows]
