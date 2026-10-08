"""Hints (Person 2): graduated, context-aware help.

practice mode -> next_hint(): levels 1-3, never code (prompt + guard + regenerate + safe fallback)
project mode  -> next_hint(): levels 1-3, short snippets allowed
                 project_help(level=4): full fix, may include code
exam / other  -> refused
"""
from __future__ import annotations

from ..models import HintRequest, HintResponse
from .client import LLMError, gemma_json, gemma_text
from .guard import check_no_code
from .prompting import render

MAX_LEVEL = 3

LEVEL_INSTRUCTIONS = {
    1: "Level 1 — NUDGE: ask one or two guiding questions that point the user toward the key "
       "observation. Do not name the algorithm or technique.",
    2: "Level 2 — CONCEPT: name the technique or data structure that fits and explain in plain "
       "words WHY it fits this problem. Do not describe the steps.",
    3: "Level 3 — PLAN: describe the approach as 3 to 5 short numbered steps in plain English. "
       "Describe ideas, not code. No variable names, no formulas in programming syntax.",
}

SAFE_FALLBACK = {
    1: "Try a tiny example by hand. What is the answer for the smallest possible input, and how "
       "would you use it to answer a slightly bigger one?",
    2: "Think about whether the answer for the full problem can be built from answers to smaller "
       "versions of the same problem, and whether you'd end up solving the same smaller problem "
       "many times.",
    3: "1. Write down what a smaller version of the problem looks like. 2. Decide how answers to "
       "smaller versions combine into a bigger answer. 3. Work out the order to solve them so each "
       "one is ready when you need it. 4. Check your idea against the examples by hand.",
}

SCHEMA = {
    "type": "object",
    "properties": {"level": {"type": "integer"}, "text": {"type": "string", "minLength": 1}},
    "required": ["level", "text"],
}


def _fmt_previous(previous: list[str]) -> str:
    return "\n".join(f"- {h}" for h in previous) if previous else "(none yet)"


def _practice_hint(req: HintRequest, level: int) -> HintResponse:
    base = dict(
        problem_title=req.problem_title or req.problem_key,
        platform=req.problem_key.split(":")[0],
        level=level,
        level_instructions=LEVEL_INSTRUCTIONS[level],
        previous_hints=_fmt_previous(req.previous_hints),
        user_context=(req.user_context or "(empty)")[:2000],
    )
    system = render("system_tutor")
    prompt = render("hint_practice", **base)
    last_reason = None
    for attempt in range(2):
        try:
            out = gemma_json(prompt, SCHEMA, system=system, temperature=0.5, use_cache=False)
        except LLMError as e:
            return HintResponse(req.signal_id, level, SAFE_FALLBACK[level], is_code=False,
                                blocked=True, block_reason=f"model unavailable: {str(e)[:80]}")
        text = out["text"].strip()
        ok, last_reason = check_no_code(text)
        if ok:
            return HintResponse(req.signal_id, level, text, is_code=False)
        prompt = render("hint_practice", **base) + (
            f"\n\nYour previous answer was rejected because it {last_reason}. "
            "Rewrite it as plain English sentences with absolutely no code-like text."
        )
    return HintResponse(req.signal_id, level, SAFE_FALLBACK[level], is_code=False,
                        blocked=True, block_reason=f"guard: {last_reason}")


def _project_hint(req: HintRequest, level: int) -> HintResponse:
    prompt = render(
        "hint_project",
        problem_title=req.problem_title or req.problem_key,
        level=level,
        level_instructions=LEVEL_INSTRUCTIONS[level].replace(
            "Describe ideas, not code. No variable names, no formulas in programming syntax.",
            "Small snippets are fine if they help."),
        previous_hints=_fmt_previous(req.previous_hints),
        user_context=(req.user_context or "(empty)")[:4000],
    )
    try:
        out = gemma_json(prompt, SCHEMA, system=render("system_tutor"), temperature=0.5, use_cache=False)
    except LLMError as e:
        return HintResponse(req.signal_id, level, SAFE_FALLBACK[level], is_code=False,
                            blocked=True, block_reason=f"model unavailable: {str(e)[:80]}")
    text = out["text"].strip()
    return HintResponse(req.signal_id, level, text, is_code="```" in text)


def next_hint(req: HintRequest) -> HintResponse:
    """Next graduated hint. Practice mode can never return code, whatever is asked."""
    level = max(1, min(int(req.level), MAX_LEVEL))
    if req.mode == "practice":
        return _practice_hint(req, level)
    if req.mode == "project":
        return _project_hint(req, level)
    return HintResponse(req.signal_id, level, "StuckPoint is switched off here.",
                        is_code=False, blocked=True, block_reason=f"mode={req.mode}")


def project_help(req: HintRequest) -> HintResponse:
    """Full fix with code — PROJECT MODE ONLY."""
    if req.mode != "project":
        raise PermissionError(f"project_help is only allowed in project mode (got {req.mode!r})")
    if req.level < 4:
        return _project_hint(req, req.level)
    prompt = render(
        "project_full",
        problem_title=req.problem_title or req.problem_key,
        user_context=(req.user_context or "(nothing pasted)")[:6000],
    )
    try:
        text = gemma_text(prompt, system=render("system_tutor").split("- When told")[0], temperature=0.3)
    except LLMError as e:
        return HintResponse(req.signal_id, 4, "Couldn't reach Gemma right now — try again in a moment.",
                            is_code=False, blocked=True, block_reason=str(e)[:120])
    return HintResponse(req.signal_id, 4, text.strip(), is_code="```" in text)
