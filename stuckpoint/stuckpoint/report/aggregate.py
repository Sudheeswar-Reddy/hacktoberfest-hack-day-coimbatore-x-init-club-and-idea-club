"""Sessions + metrics (Person 1). `compute_metrics` is the single source of truth
for every number in the skills report; the evidence gate checks Gemma against it.

Definitions (also in the README):
  active_min           sum of Activity Frames `duration_min` over the problem's frames
                       (localhost / terminal frames count toward the current project)
  stuck_episodes       stuck signals for the problem that were confirmed by rules or Gemma
  hints_used           hints served for the problem
  solved               only what the user marked with "Solved ✓" — never guessed
  time_to_unstuck_min  minutes from the first hint to the next frame on that problem
                       with a typing rate >= 15 keys/min (None if that never happened)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from ..context.classifier import classify
from ..models import SessionRecord

UNSTUCK_KPM = 15.0


def _ts(frame: dict, field: str) -> str:
    return f"{frame.get('_day', '')}T{frame.get(field, '')}".lstrip("T")


def _parse(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


def _default_tagger(title, platform):
    from ..llm.topics import tag_topics

    return tag_topics(title, platform)


def build_sessions(frames: list[dict], store=None, tagger=None) -> list[SessionRecord]:
    """Group frames into one SessionRecord per problem_key (practice + project only)."""
    tagger = tagger or _default_tagger
    ordered = sorted(frames, key=lambda f: (f.get("_day", ""), f.get("start", "")))
    groups: dict[str, dict] = {}
    current_project: Optional[str] = None

    for f in ordered:
        lab = classify(f)
        if lab.mode not in ("practice", "project"):
            continue
        key = lab.problem_key
        if key is None and lab.mode == "project":
            key = current_project               # localhost / terminal -> current project
        if key is None:
            continue
        if key.startswith("project:"):
            current_project = key
        g = groups.setdefault(key, {"label": lab if lab.problem_key else None, "frames": []})
        if g["label"] is None and lab.problem_key:
            g["label"] = lab
        g["frames"].append(f)

    sessions = []
    for key, g in groups.items():
        fs, lab = g["frames"], g["label"]
        title = lab.problem_title if lab else key.split(":", 1)[-1]
        platform = lab.platform if lab else key.split(":", 1)[0]
        mode = lab.mode if lab else ("project" if key.startswith("project:") else "practice")
        signals = store.signals_for(key) if store else []
        hints = store.hints_for(key) if store else []
        sessions.append(SessionRecord(
            problem_key=key,
            problem_title=title,
            platform=platform,
            mode=mode,
            topics=list(tagger(title, platform) or ["other"]),
            first_seen=_ts(fs[0], "start"),
            last_seen=_ts(fs[-1], "end"),
            active_min=round(sum(float(f.get("duration_min") or 0) for f in fs), 1),
            stuck_episodes=sum(1 for s in signals if s.status in
                               ("confirmed", "offered", "accepted", "dismissed", "snoozed")),
            hints_used=len(hints),
            max_hint_level=max((h.level for h in hints), default=0),
            time_to_unstuck_min=_time_to_unstuck(fs, store.hint_times(key) if store else []),
            solved=store.is_solved(key) if store else None,
            frame_ids=[f["id"] for f in fs],
        ))
    return sessions


def _time_to_unstuck(frames: list[dict], hint_times: list[str]) -> Optional[float]:
    if not hint_times:
        return None
    first_hint = _parse(hint_times[0])
    if first_hint is None:
        return None
    for f in frames:
        start = _parse(_ts(f, "start"))
        if start is None or start <= first_hint:
            continue
        dur = float(f.get("duration_min") or 0)
        keys = (f.get("input") or {}).get("keys", 0)
        if dur > 0 and keys / dur >= UNSTUCK_KPM:
            return round((start - first_hint).total_seconds() / 60, 1)
    return None


def compute_metrics(sessions: list[SessionRecord]) -> dict:
    """Shape (instructions Part 4, P1) — P2's prompt and evidence gate depend on it."""
    topics: dict[str, dict] = {}
    for s in sessions:
        for t in s.topics:
            m = topics.setdefault(t, {"problems": 0, "_active": 0.0, "stuck_episodes": 0,
                                      "hints_used": 0, "solved": 0, "problem_keys": [], "_ttu": []})
            m["problems"] += 1
            m["_active"] += s.active_min
            m["stuck_episodes"] += s.stuck_episodes
            m["hints_used"] += s.hints_used
            m["solved"] += 1 if s.solved else 0
            m["problem_keys"].append(s.problem_key)
            if s.time_to_unstuck_min is not None:
                m["_ttu"].append(s.time_to_unstuck_min)

    out_topics = {}
    for t, m in sorted(topics.items()):
        row = {"problems": m["problems"],
               "avg_active_min": round(m["_active"] / m["problems"], 1),
               "stuck_episodes": m["stuck_episodes"],
               "hints_used": m["hints_used"],
               "solved": m["solved"],
               "problem_keys": m["problem_keys"]}
        if m["_ttu"]:
            row["avg_time_to_unstuck_min"] = round(sum(m["_ttu"]) / len(m["_ttu"]), 1)
        out_topics[t] = row

    return {
        "topics": out_topics,
        "overall": {
            "problems": len(sessions),
            "total_active_min": round(sum(s.active_min for s in sessions), 1),
            "stuck_episodes": sum(s.stuck_episodes for s in sessions),
            "hints_used": sum(s.hints_used for s in sessions),
            "solved": sum(1 for s in sessions if s.solved),
        },
    }
