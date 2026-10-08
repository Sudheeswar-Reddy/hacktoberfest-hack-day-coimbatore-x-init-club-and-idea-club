"""build_report (Person 2): frames -> sessions -> metrics -> Gemma claims -> gate."""
from __future__ import annotations

from ..capture.source import report_frames
from ..llm.report_draft import draft_report_claims
from ..store.db import Store
from .aggregate import build_sessions, compute_metrics
from .gate import run_gate, summarize


def build_report(store: Store | None = None) -> dict:
    store = store or Store()
    try:
        frames = report_frames()
    except FileNotFoundError:          # no capture data yet
        frames = []
    sessions = build_sessions(frames, store)
    metrics = compute_metrics(sessions)
    drafted = draft_report_claims(metrics) if sessions else []
    claims = run_gate(drafted, metrics, sessions)
    store.save_sessions(sessions)
    store.save_claims(claims)
    return {
        "metrics": metrics,
        "sessions": [s.to_dict() for s in sessions],
        "claims": [c.to_dict() for c in claims],
        "gate_summary": summarize(claims),
        "llm_available": bool(drafted) or not sessions,
    }
