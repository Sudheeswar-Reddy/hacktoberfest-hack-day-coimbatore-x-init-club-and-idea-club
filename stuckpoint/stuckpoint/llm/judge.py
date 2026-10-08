"""judge_stuck (Person 2): Gemma decides borderline stuck signals."""
from __future__ import annotations

from ..models import StuckSignal
from .client import LLMError, gemma_json
from .prompting import render

MAX_FRAMES = 40

SCHEMA = {
    "type": "object",
    "properties": {
        "stuck": {"type": "boolean"},
        "reason": {"type": "string", "maxLength": 300},
    },
    "required": ["stuck", "reason"],
}


def _compact(frames: list[dict], frame_ids: list[str]) -> str:
    wanted = set(frame_ids)
    rows = []
    for f in frames:
        if f.get("id") not in wanted:
            continue
        title = (f.get("windows") or [""])[0][:80]
        keys = (f.get("input") or {}).get("keys", 0)
        rows.append(f"{f.get('app','?')} | {f.get('site','-')} | {title} | "
                    f"{f.get('duration_min', 0)} | {keys}")
    return "\n".join(rows[-MAX_FRAMES:]) or "(none)"


def judge_stuck(signal: StuckSignal, frames: list[dict]) -> tuple[bool, str]:
    """Return (is_stuck, one-sentence reason). Never raises."""
    prompt = render(
        "judge_stuck",
        problem_title=signal.problem_title or signal.problem_key,
        platform=signal.platform,
        mode=signal.mode,
        minutes=signal.minutes_on_problem,
        loops=signal.loops,
        kpm=signal.keys_per_min,
        rules=", ".join(signal.rules_fired),
        frames=_compact(frames, signal.frame_ids),
    )
    try:
        out = gemma_json(prompt, SCHEMA, system=render("system_tutor"), temperature=0.2)
        return bool(out["stuck"]), out["reason"].strip()
    except LLMError as e:
        # Fallback: trust the rules only if at least two fired.
        stuck = len(signal.rules_fired) >= 2
        return stuck, f"Gemma unavailable ({str(e)[:60]}); decided by rules: {', '.join(signal.rules_fired)}"
