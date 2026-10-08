import json
from pathlib import Path

from stuckpoint.models import ReportClaim, SessionRecord
from stuckpoint.report.gate import run_gate, summarize

SAMPLE = json.loads((Path(__file__).resolve().parent.parent / "fixtures" / "sample_claims.json")
                    .read_text(encoding="utf-8"))


def _session(key, topics):
    return SessionRecord(problem_key=key, problem_title=key, platform="leetcode", mode="practice",
                         topics=topics, first_seen="", last_seen="", active_min=1, stuck_episodes=0,
                         hints_used=0, max_hint_level=0, time_to_unstuck_min=None, solved=None,
                         frame_ids=[])


SESSIONS = [_session("leetcode:two-sum", ["hashing", "arrays"]),
            _session("leetcode:coin-change", ["dynamic-programming", "arrays"]),
            _session("project:todo-api", ["http-apis"])]


def _gated():
    claims = [ReportClaim.from_dict(c) for c in SAMPLE["claims"]]
    return {c.id: c for c in run_gate(claims, SAMPLE["metrics"], SESSIONS)}


def test_planted_wrong_number_rejected():
    c = _gated()["clm-bad001"]
    assert c.gate_status == "rejected"
    assert "avg_active_min claimed 25, measured 34.3" in c.gate_reason
    assert c.recomputed == {"avg_active_min": 34.3}


def test_unknown_problem_rejected():
    c = _gated()["clm-bad002"]
    assert c.gate_status == "rejected" and "leetcode:number-of-islands" in c.gate_reason


def test_thin_evidence_downgraded():
    c = _gated()["clm-thin01"]
    assert c.gate_status == "downgraded" and c.confidence == "speculative"


def test_good_claims_pass():
    g = _gated()
    assert g["clm-good01"].gate_status == "passed"
    assert g["clm-good02"].gate_status == "passed"


def test_summary():
    s = summarize(list(_gated().values()))
    assert s == {"total": 6, "passed": 2, "downgraded": 2, "rejected": 2}


def _claim(**kw):
    base = dict(id="c", kind="weakness", text="", topic="arrays", numeric_claims={},
                about_problems=[], confidence="medium")
    return ReportClaim(**{**base, **kw})


def test_number_only_in_text_rejected():
    [c] = run_gate([_claim(text="You spent 99 minutes on arrays.", numeric_claims={"problems": 2})],
                   SAMPLE["metrics"], SESSIONS)
    assert c.gate_status == "rejected" and "99" in c.gate_reason


def test_minute_tolerance_and_big_o():
    [c] = run_gate([_claim(text="Arrays took 24 minutes on average; aim for O(n) solutions.",
                           numeric_claims={"avg_active_min": 24.0})], SAMPLE["metrics"], SESSIONS)
    assert c.gate_status == "passed"


def test_unknown_topic_and_key_rejected():
    [a, b] = run_gate([_claim(topic="graphs"), _claim(numeric_claims={"vibes": 3})],
                      SAMPLE["metrics"], SESSIONS)
    assert a.gate_status == "rejected" and b.gate_status == "rejected"
