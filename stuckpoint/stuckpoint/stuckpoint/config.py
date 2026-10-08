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
    p = Path(value)
    return str(p if p.is_absolute() else ROOT / p)


# --- Gemma 4 (Person 2) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMMA_MODEL = os.getenv("GEMMA_MODEL", "gemma-4-31b-it")
LLM_TIMEOUT_S = _int("LLM_TIMEOUT_S", 20)
LLM_LOG = _path("LLM_LOG", "logs/llm.jsonl")

# --- Activity source (Person 1) ---
SOURCE = os.getenv("STUCKPOINT_SOURCE", "live").strip().lower()
FIXTURE = _path("STUCKPOINT_FIXTURE", "fixtures/sample_frames.json")
AFRAMES_DB = os.getenv("AFRAMES_DB") or None

# --- Cross-platform recorder (capture/recorder.py) ---
# Nocta-schema capture DB written by `python -m stuckpoint record` on any OS.
RECORDER_DB = str(Path(os.getenv("RECORDER_DB") or "~/.activity-frames/stuckpoint-capture.sqlite").expanduser())
RECORDER_POLL_S = _float("RECORDER_POLL_S", 2.0)          # how often focus is sampled
RECORDER_HEARTBEAT_S = _float("RECORDER_HEARTBEAT_S", 10.0)  # frame every N s while present
RECORDER_IDLE_S = _float("RECORDER_IDLE_S", 600.0)        # no input this long = away

# --- Local app DB (Person 3) ---
STUCKPOINT_DB = _path("STUCKPOINT_DB", "stuckpoint.db")

# --- Stuck detection (Person 1) ---
STUCK_THRESHOLD_MIN = _float("STUCK_THRESHOLD_MIN", 15)
LOOP_THRESHOLD = _int("LOOP_THRESHOLD", 3)
LOW_INPUT_MIN = _float("LOW_INPUT_MIN", 10)
LOW_INPUT_KPM = _float("LOW_INPUT_KPM", 8)
WINDOW_MIN = _float("WINDOW_MIN", 30)
CHECK_INTERVAL_S = _int("CHECK_INTERVAL_S", 60)
COOLDOWN_MIN = _float("COOLDOWN_MIN", 10)
SNOOZE_MIN = _float("SNOOZE_MIN", 15)
