"""Evidence gate (Person 2): "Gemma proposes; code verifies."

Every claim Gemma drafts is checked against the measured metrics before it is shown:
  1. Number check     every numeric_claims[key] equals metrics[topic][key]
                      (±0.5 for minute values, exact for counts)
  2. Evidence check   every about_problems key exists in the sessions and has the claim's topic
  3. Text check       every number written in the sentence is backed by numeric_claims
  4. Sufficiency      fewer than 2 problems behind a claim caps confidence at "speculative"

Outcome: any mismatch -> rejected (with a precise reason); only the cap -> downgraded;
otherwise passed.
"""
from __future__ import annotations

import re
from dataclasses import replace

from ..models import ReportClaim, SessionRecord

MINUTE_TOLERANCE = 0.5
_NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w])")
_BIG_O = re.compile(r"O\([^)]*\)")


def _is_minutes(key: str) -> bool:
    return "min" in key


def _matches(key: str, claimed, measured) -> bool:
    try:
        c, m = float(claimed), float(measured)
    except (TypeError, ValueError):
        return False
    if _is_minutes(key):
        return abs(c - m) <= MINUTE_TOLERANCE
    return abs(c - m) < 1e-9


def _fmt(v) -> str:
    return f"{v:g}" if isinstance(v, (int, float)) else repr(v)


def check_claim(claim: ReportClaim, metrics: dict, sessions: list[SessionRecord]) -> ReportClaim:
    topics = metrics.get("topics", {})
    if claim.topic is None:
        scope, scope_name = metrics.get("overall", {}), "overall"
    elif claim.topic in topics:
        scope, scope_name = topics[claim.topic], claim.topic
    else:
        return replace(claim, gate_status="rejected",
                       gate_reason=f"topic '{claim.topic}' has no measured data")

    problems: list[str] = []
    recomputed: dict = {}

    # 1. numbers
    for key, value in (claim.numeric_claims or {}).items():
        if key not in scope or key == "problem_keys":
            problems.append(f"'{key}' is not a measured metric for {scope_name}")
            continue
        recomputed[key] = scope[key]
        if not _matches(key, value, scope[key]):
            problems.append(f"{key} claimed {_fmt(value)}, measured {_fmt(scope[key])}")

    # 2. evidence
    by_key = {s.problem_key: s for s in sessions}
    for pk in claim.about_problems or []:
        s = by_key.get(pk)
        if s is None:
            problems.append(f"cites {pk}, not in sessions")
        elif claim.topic and claim.topic not in s.topics:
            problems.append(f"cites {pk}, which is not tagged {claim.topic}")

    # 3. numbers inside the sentence
    claimed_values = [v for v in (claim.numeric_claims or {}).values() if isinstance(v, (int, float))]
    for n in _NUMBER.findall(_BIG_O.sub("", claim.text)):
        x = float(n)
        if not any(abs(x - float(v)) < 0.051 or round(float(v)) == x for v in claimed_values):
            problems.append(f"text mentions {n}, which is not in numeric_claims")

    if problems:
        return replace(claim, gate_status="rejected", gate_reason="; ".join(problems),
                       recomputed=recomputed)

    # 4. sufficiency
    n_problems = scope.get("problems", 0)
    if n_problems < 2 and claim.confidence != "speculative":
        return replace(claim, gate_status="downgraded", confidence="speculative",
                       recomputed=recomputed,
                       gate_reason=f"only {n_problems} problem(s) in {scope_name}: "
                                   f"confidence capped at speculative (was {claim.confidence})")
    return replace(claim, gate_status="passed", gate_reason=None, recomputed=recomputed)


def run_gate(claims: list[ReportClaim], metrics: dict, sessions: list[SessionRecord]) -> list[ReportClaim]:
    return [check_claim(c, metrics, sessions) for c in claims]


def summarize(claims: list[ReportClaim]) -> dict:
    out = {"total": len(claims), "passed": 0, "downgraded": 0, "rejected": 0}
    for c in claims:
        if c.gate_status in out:
            out[c.gate_status] += 1
    return out
