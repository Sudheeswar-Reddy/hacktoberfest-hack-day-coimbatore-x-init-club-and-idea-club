"""Stuck detector (Person 1). Deterministic rules over measured frames.

Rules (instructions.md, Person 1):
  R1_time       minutes on the current problem (incl. help detours) >= STUCK_THRESHOLD_MIN
  R2_loop       >= LOOP_THRESHOLD cycles of  problem -> help -> same problem
  R3_low_input  on the problem >= LOW_INPUT_MIN and keystrokes/min < LOW_INPUT_KPM

Decision:
  R1 and (R2 or R3)  -> confident signal          (needs_judgement=False)
  any other rule hit -> borderline, ask Gemma     (needs_judgement=True)
  exam / other       -> never

Only the problem the user is on *right now* can produce a signal.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from .. import config
from ..context.classifier import classify, is_help
from ..models import ContextLabel, StuckSignal


@dataclass
class _ProblemStats:
    label: ContextLabel
    work_min: float = 0.0
    help_min: float = 0.0
    keys: int = 0
    loops: int = 0
    frame_ids: list[str] = field(default_factory=list)


def parse_clock(hms: str, now: datetime) -> datetime:
    """Activity Frames gives local 'HH:MM[:SS]'. Anchor it to now's date,
    stepping back a day if that would put it in the future (midnight wrap)."""
    fmt = "%H:%M:%S" if hms.count(":") == 2 else "%H:%M"
    t = datetime.strptime(hms, fmt).time()
    dt = datetime.combine(now.date(), t)
    if dt > now + timedelta(minutes=1):
        dt -= timedelta(days=1)
    return dt


def _in_window(frames: list[dict], now: datetime) -> list[dict]:
    cutoff = now - timedelta(minutes=config.WINDOW_MIN)
    out = [f for f in frames if parse_clock(f["end"], now) >= cutoff]
    return sorted(out, key=lambda f: parse_clock(f["start"], now))


def _cooldown_active(store, key: str, now: datetime) -> bool:
    if store is None:
        return False
    try:
        last = store.last_signal_for(key)
    except Exception:  # store problems must never stop detection
        return False
    if last is None:
        return False
    try:
        created = datetime.fromisoformat(last.created_at)
    except (TypeError, ValueError):
        return False
    age_min = (now - created).total_seconds() / 60
    if last.status == "snoozed":
        return age_min < config.SNOOZE_MIN
    return age_min < config.COOLDOWN_MIN


def analyze(frames: list[dict], now: datetime) -> tuple[Optional[str], dict[str, _ProblemStats]]:
    """Walk the window and attribute every frame. Returns (current_key, stats)."""
    stats: dict[str, _ProblemStats] = {}
    current: Optional[str] = None
    prev: Optional[str] = None          # "problem" | "help"
    last_problem_key: Optional[str] = None

    for f in _in_window(frames, now):
        label = classify(f)
        dur = float(f.get("duration_min") or 0.0)
        keys = int((f.get("input") or {}).get("keys", 0))

        if label.mode == "exam":
            current, prev = None, None
            last_problem_key = None
            continue

        key = label.problem_key
        if key is None and label.mode == "project" and current and current.startswith("project:"):
            key = current                       # localhost / terminal -> current project

        if key and label.mode in ("practice", "project"):
            s = stats.setdefault(key, _ProblemStats(label=label if label.problem_key else stats[current].label))
            if prev == "help" and last_problem_key == key:
                s.loops += 1
            s.work_min += dur
            s.keys += keys
            s.frame_ids.append(f["id"])
            current, prev, last_problem_key = key, "problem", key
        elif current and is_help(f):
            s = stats[current]
            s.help_min += dur
            s.frame_ids.append(f["id"])
            prev = "help"
        # anything else (Slack, music, ...) is ignored: it neither breaks nor extends a loop

    return current, stats


def detect(frames: list[dict], now: datetime, store=None) -> list[StuckSignal]:
    """Return at most one StuckSignal: for the problem the user is on right now."""
    if not frames:
        return []
    window = _in_window(frames, now)
    if not window or classify(window[-1]).mode == "exam":
        return []

    current, stats = analyze(frames, now)
    if not current:
        return []
    s = stats[current]
    if s.label.mode not in ("practice", "project"):
        return []

    minutes = round(s.work_min + s.help_min, 1)
    kpm = round(s.keys / s.work_min, 1) if s.work_min > 0 else 0.0
    low_input_min = min(config.LOW_INPUT_MIN, config.STUCK_THRESHOLD_MIN)

    rules: list[str] = []
    if minutes >= config.STUCK_THRESHOLD_MIN:
        rules.append("R1_time")
    if s.loops >= config.LOOP_THRESHOLD:
        rules.append("R2_loop")
    if s.work_min >= low_input_min and kpm < config.LOW_INPUT_KPM:
        rules.append("R3_low_input")
    if not rules:
        return []

    if _cooldown_active(store, current, now):
        return []

    confident = "R1_time" in rules and ("R2_loop" in rules or "R3_low_input" in rules)
    return [StuckSignal(
        id=f"sig-{uuid.uuid4().hex[:8]}",
        created_at=now.isoformat(timespec="seconds"),
        problem_key=current,
        problem_title=s.label.problem_title,
        mode=s.label.mode,
        platform=s.label.platform,
        minutes_on_problem=minutes,
        loops=s.loops,
        keys_per_min=kpm,
        rules_fired=rules,
        frame_ids=list(s.frame_ids),
        needs_judgement=not confident,
    )]
