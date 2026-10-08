"""Central configuration. Every setting comes from the environment (.env)."""
from __future__ import annotations

import os
from pathlib import Path

try:  # optional: load .env if python-dotenv is installed
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parent.parent


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _path(name: str, default: str) -> str:
    value = os.getenv(name) or default
    p = Path(value).expanduser()
    return str(p if p.is_absolute() else ROOT / p)


# --- Gemma 4 (Person 2) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMMA_MODEL = os.getenv("GEMMA_MODEL", "gemma-4-31b-it")
LLM_TIMEOUT_S = _int("LLM_TIMEOUT_S", 30)
# Gemma 4 "thinking": minimal keeps replies fast (a code review: ~6 s instead of ~146 s).
# minimal | low | medium | high | default (= don't send a thinking setting)
GEMMA_THINKING = os.getenv("GEMMA_THINKING", "minimal").strip().lower()
LLM_LOG = _path("LLM_LOG", "logs/llm.jsonl")

# --- Activity source (Person 1) ---
SOURCE = os.getenv("STUCKPOINT_SOURCE", "live").strip().lower()
FIXTURE = _path("STUCKPOINT_FIXTURE", "fixtures/sample_frames.json")
# Capture DB in Activity Frames' schema. Written by ingest.py (extension events)
# and by the OS recorder; read by the Activity Frames compiler.
AFRAMES_DB = _path("AFRAMES_DB", "data/capture.sqlite")
AFRAMES_DB_EXPLICIT = bool(os.getenv("AFRAMES_DB"))   # set -> never look elsewhere

# --- Optional OS-level recorder (capture/recorder.py), for capture without the extensions ---
RECORDER_DB = _path("RECORDER_DB", AFRAMES_DB)
RECORDER_POLL_S = _float("RECORDER_POLL_S", 2.0)          # how often focus is sampled
RECORDER_HEARTBEAT_S = _float("RECORDER_HEARTBEAT_S", 10.0)  # frame every N s while present
RECORDER_IDLE_S = _float("RECORDER_IDLE_S", 600.0)        # no input this long = away

# --- Local app DB (signals, hints, solved marks, claims) ---
STUCKPOINT_DB = _path("STUCKPOINT_DB", "data/stuckpoint.db")

# --- Local engine (server.py) ---
ENGINE_HOST = os.getenv("ENGINE_HOST", "127.0.0.1")
ENGINE_PORT = _int("ENGINE_PORT", 8765)
REPORT_DAYS = _int("REPORT_DAYS", 7)              # how much history the report covers
SUGGEST_MAX_LINES = _int("SUGGEST_MAX_LINES", 300)

# --- Stuck detection (Person 1) ---
STUCK_THRESHOLD_MIN = _float("STUCK_THRESHOLD_MIN", 15)
LOOP_THRESHOLD = _int("LOOP_THRESHOLD", 3)
LOW_INPUT_MIN = _float("LOW_INPUT_MIN", 10)
LOW_INPUT_KPM = _float("LOW_INPUT_KPM", 8)
WINDOW_MIN = _float("WINDOW_MIN", 30)
CHECK_INTERVAL_S = _int("CHECK_INTERVAL_S", 60)
COOLDOWN_MIN = _float("COOLDOWN_MIN", 10)
SNOOZE_MIN = _float("SNOOZE_MIN", 15)
