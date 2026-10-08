"""Optional OS-level capture recorder (Person 1).

In v2 the Chrome / VS Code extensions are the primary recorder (see ingest.py).
This recorder is the fallback for capturing WITHOUT the extensions. It writes
into the same capture DB (config.AFRAMES_DB). Use one or the other, not both.

Activity Frames' own engine (`aframes record` -> nocta-recorder) ships only for
macOS. Its *compiler* is recorder-agnostic: it reads any SQLite database with
the nocta `frames` / `ui_events` / `elements` tables. This module is that
recorder for Windows, Linux and macOS, so the unmodified `activity_frames`
package compiles our data exactly as it compiles nocta's.

What is written (privacy rules from the README):
  frames     one row per focus change + a heartbeat every HEARTBEAT_S while the
             user is present: app, window title, browser URL. No screenshots.
  ui_events  one row per key press ('key') or mouse click ('click').
             Key rows carry NO key code and NO text - only the fact of a press.
  elements   created empty (we don't capture accessibility trees).

    python -m stuckpoint record              # foreground, Ctrl+C to stop
    python -m stuckpoint record --background
    python -m stuckpoint record --status | --stop
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .. import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP NOT NULL,
    app_name TEXT, window_name TEXT, focused BOOLEAN,
    browser_url TEXT, document_path TEXT,
    device_name TEXT NOT NULL DEFAULT 'monitor_1',
    url_source TEXT              -- ours: 'browser' (address bar) | 'title' (inferred) | 'chrome' | 'vscode' (extensions)
);
CREATE INDEX IF NOT EXISTS idx_frames_ts ON frames(timestamp);
CREATE TABLE IF NOT EXISTS ui_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    event_type TEXT NOT NULL,
    x INTEGER, y INTEGER,
    text_content TEXT,
    app_name TEXT, window_title TEXT, browser_url TEXT,
    element_name TEXT, element_role TEXT
);
CREATE INDEX IF NOT EXISTS idx_ui_events_ts ON ui_events(timestamp);
CREATE TABLE IF NOT EXISTS elements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    frame_id INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'accessibility',
    role TEXT NOT NULL DEFAULT 'AXButton',
    text TEXT,
    left_bound REAL, top_bound REAL, width_bound REAL, height_bound REAL
);
"""

HOME = Path("~/.activity-frames").expanduser()
PID_FILE = HOME / "stuckpoint-recorder.pid"
STOP_FILE = HOME / "stuckpoint-recorder.stop"
LOG_FILE = HOME / "stuckpoint-recorder.log"


@dataclass(frozen=True)
class Focus:
    app: str
    title: str
    url: Optional[str] = None
    url_source: Optional[str] = None   # 'browser' | 'title'


def utc_ts(dt: datetime | None = None) -> str:
    """Recorder timestamp format, identical to nocta's: UTC ISO with micros."""
    dt = dt or datetime.now(timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")


def open_db(path: str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")   # activity_frames reads while we write
    conn.executescript(SCHEMA)
    return conn


def get_backend():
    """Platform backend: foreground(), idle_seconds(), start_input(cb), stop_input()."""
    if sys.platform == "win32":
        from .backends.windows import WindowsBackend
        return WindowsBackend()
    if sys.platform == "darwin":
        from .backends.macos import MacBackend
        return MacBackend()
    from .backends.linux import LinuxBackend
    return LinuxBackend()


class Recorder:
    def __init__(self, db_path: str, backend, *, poll_s: float = config.RECORDER_POLL_S,
                 heartbeat_s: float = config.RECORDER_HEARTBEAT_S,
                 idle_s: float = config.RECORDER_IDLE_S,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.conn = open_db(db_path)
        self.backend = backend
        self.poll_s, self.heartbeat_s, self.idle_s = poll_s, heartbeat_s, idle_s
        self.clock = clock
        self._events: deque = deque()        # (utc_ts, type, x, y) from the input thread
        self._last_focus: Optional[Focus] = None
        self._last_frame_at = 0.0
        self.frames_written = 0
        self.events_written = 0

    # called from the input-hook thread: must be cheap
    def on_input(self, event_type: str, x: Optional[int] = None, y: Optional[int] = None) -> None:
        self._events.append((utc_ts(self.clock()), event_type, x, y))

    def tick(self) -> None:
        """One poll: write a frame if focus changed (or heartbeat), flush input."""
        focus = self.backend.foreground()
        now = self.clock()
        idle = self.backend.idle_seconds()
        if focus and focus.app:
            changed = focus != self._last_focus
            due = now.timestamp() - self._last_frame_at >= self.heartbeat_s
            if changed or (due and idle < self.idle_s):
                self.conn.execute(
                    "INSERT INTO frames (timestamp, app_name, window_name, focused, browser_url,"
                    " url_source) VALUES (?,?,?,1,?,?)",
                    (utc_ts(now), focus.app, focus.title or None, focus.url, focus.url_source),
                )
                self.frames_written += 1
                self._last_frame_at = now.timestamp()
            self._last_focus = focus
        self._flush_events(focus)
        self.conn.commit()

    def _flush_events(self, focus: Optional[Focus]) -> None:
        rows = []
        while self._events:
            ts, etype, x, y = self._events.popleft()
            rows.append((ts, etype, x, y,
                         focus.app if focus else None,
                         focus.title if focus else None,
                         focus.url if focus else None))
        if rows:
            self.conn.executemany(
                "INSERT INTO ui_events (timestamp, event_type, x, y, app_name, window_title,"
                " browser_url) VALUES (?,?,?,?,?,?,?)", rows)
            self.events_written += len(rows)

    def run(self, stop: threading.Event | None = None, verbose: bool = True) -> None:
        stop = stop or threading.Event()
        STOP_FILE.unlink(missing_ok=True)
        self.backend.start_input(self.on_input)
        if verbose:
            print(f"[recorder] writing to {config.RECORDER_DB} (Ctrl+C to stop)")
        last_report = time.time()
        try:
            while not stop.is_set() and not STOP_FILE.exists():
                try:
                    self.tick()
                except sqlite3.Error as e:
                    print(f"[recorder] db error: {e}", file=sys.stderr)
                except Exception as e:  # a backend hiccup must not stop capture
                    print(f"[recorder] {type(e).__name__}: {e}", file=sys.stderr)
                if verbose and time.time() - last_report > 60:
                    print(f"[recorder] {self.frames_written} frames, {self.events_written} input events")
                    last_report = time.time()
                stop.wait(self.poll_s)
        finally:
            self.backend.stop_input()
            self.conn.commit()
            self.conn.close()
            STOP_FILE.unlink(missing_ok=True)


# ---- process management (start / stop / status) ---------------------------

def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":  # os.kill(pid, 0) would TERMINATE the process on Windows
        import ctypes

        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == 259     # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_pid() -> Optional[int]:
    try:
        pid = int(PID_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None
    if _pid_alive(pid):
        return pid
    PID_FILE.unlink(missing_ok=True)
    return None


def status() -> str:
    pid = _read_pid()
    state = f"recording (pid {pid})" if pid else "not recording"
    try:
        conn = sqlite3.connect(Path(config.RECORDER_DB).resolve().as_uri() + "?mode=ro", uri=True)
        last, n = conn.execute("SELECT MAX(timestamp), COUNT(*) FROM frames").fetchone()
        conn.close()
    except sqlite3.Error:
        return f"{state}; no capture database yet at {config.RECORDER_DB}"
    if not last:
        return f"{state}; database empty"
    age = time.time() - datetime.fromisoformat(last).timestamp()
    return f"{state}; {n} frames, last {int(age)}s ago; db {config.RECORDER_DB}"


def record(background: bool = False) -> None:
    # The detached child skips this check: its parent already wrote a pid, and on
    # Windows a venv python.exe is a launcher, so that pid isn't even the child's.
    is_child = os.environ.pop("STUCKPOINT_RECORDER_CHILD", "") == "1"
    if not is_child and _read_pid():
        print("Already " + status())
        return
    if background:
        HOME.mkdir(parents=True, exist_ok=True)
        log = open(LOG_FILE, "ab")
        kwargs: dict = {"stdout": log, "stderr": log, "stdin": subprocess.DEVNULL,
                        "env": {**os.environ, "STUCKPOINT_RECORDER_CHILD": "1",
                                "PYTHONUNBUFFERED": "1"}}
        if sys.platform == "win32":
            kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        proc = subprocess.Popen([sys.executable, "-m", "stuckpoint", "record"],
                                cwd=str(config.ROOT), **kwargs)
        PID_FILE.write_text(str(proc.pid))
        print(f"Capture started in background (pid {proc.pid}). Log: {LOG_FILE}\n"
              "Stop with: python -m stuckpoint record --stop")
        return
    HOME.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    try:
        Recorder(config.RECORDER_DB, get_backend()).run()
    except KeyboardInterrupt:
        print("\n[recorder] stopped")
    finally:
        PID_FILE.unlink(missing_ok=True)


def stop_recording() -> None:
    pid = _read_pid()
    if not pid:
        print("Not recording.")
        return
    STOP_FILE.parent.mkdir(parents=True, exist_ok=True)
    STOP_FILE.touch()                      # graceful: the loop checks this every poll
    for _ in range(int(config.RECORDER_POLL_S * 4) + 10):
        if not _pid_alive(pid):
            break
        time.sleep(0.5)
    else:
        import signal
        os.kill(pid, signal.SIGTERM)
    PID_FILE.unlink(missing_ok=True)
    print("Capture stopped.")
