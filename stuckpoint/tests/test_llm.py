"""Gemma layer tests with the API mocked — no key or network needed."""
import pytest

from stuckpoint.llm import client, hints, judge, report_draft, topics
from stuckpoint.llm.client import LLMError, extract_json
from stuckpoint.models import HintRequest, StuckSignal


def test_extract_json_variants():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! {"a": 1} hope that helps') == {"a": 1}
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_gemma_json_retries_then_validates(monkeypatch):
    replies = iter(["not json", '{"stuck": true, "reason": "3 loops"}'])
    monkeypatch.setattr(client, "_raw_call", lambda *a, **k: next(replies))
    out = client.gemma_json("p", judge.SCHEMA, use_cache=False)
    assert out == {"stuck": True, "reason": "3 loops"}


def test_gemma_json_raises_after_retries(monkeypatch):
    monkeypatch.setattr(client, "_raw_call", lambda *a, **k: '{"wrong": 1}')
    with pytest.raises(LLMError):
        client.gemma_json("p", judge.SCHEMA, use_cache=False)


def _req(mode="practice", level=1, ctx=None):
    return HintRequest(signal_id="sig-1", problem_key="leetcode:coin-change",
                       problem_title="Coin Change", mode=mode, level=level, user_context=ctx)


def test_practice_hint_ok(monkeypatch):
    monkeypatch.setattr(hints, "gemma_json",
                        lambda *a, **k: {"level": 1, "text": "What is the answer for amount zero?"})
    r = hints.next_hint(_req())
    assert not r.blocked and not r.is_code and "amount zero" in r.text


def test_practice_hint_regenerates_after_code(monkeypatch):
    replies = iter([{"level": 3, "text": "```python\ndef f(): pass\n```"},
                    {"level": 3, "text": "1. Consider every amount. 2. Keep the smallest count."}])
    monkeypatch.setattr(hints, "gemma_json", lambda *a, **k: next(replies))
    r = hints.next_hint(_req(level=3, ctx="just give me the code"))
    assert not r.blocked and "```" not in r.text


def test_practice_hint_never_returns_code(monkeypatch):
    monkeypatch.setattr(hints, "gemma_json",
                        lambda *a, **k: {"level": 3, "text": "dp[i] = min(dp[i], dp[i-c] + 1)"})
    r = hints.next_hint(_req(level=3))
    assert r.blocked and r.text == hints.SAFE_FALLBACK[3] and not r.is_code


def test_practice_hint_model_down(monkeypatch):
    def boom(*a, **k):
        raise LLMError("rate limited")
    monkeypatch.setattr(hints, "gemma_json", boom)
    r = hints.next_hint(_req(level=2))
    assert r.blocked and r.text == hints.SAFE_FALLBACK[2]


def test_level_is_clamped(monkeypatch):
    monkeypatch.setattr(hints, "gemma_json", lambda *a, **k: {"level": 3, "text": "Plan in words."})
    assert hints.next_hint(_req(level=9)).level == 3


def test_exam_mode_refused():
    r = hints.next_hint(_req(mode="exam"))
    assert r.blocked


def test_project_help_only_in_project_mode():
    with pytest.raises(PermissionError):
        hints.project_help(_req(mode="practice", level=4))


def test_project_full_code(monkeypatch):
    monkeypatch.setattr(hints, "gemma_text",
                        lambda *a, **k: "Root cause: missing CORS.\n```python\napp.add_middleware(...)\n```")
    r = hints.project_help(_req(mode="project", level=4, ctx="CORS error"))
    assert r.is_code and not r.blocked


def _sig(rules):
    return StuckSignal(id="sig-1", created_at="2026-10-08T20:46:30", problem_key="leetcode:coin-change",
                       problem_title="Coin Change", mode="practice", platform="leetcode",
                       minutes_on_problem=16, loops=3, keys_per_min=30, rules_fired=rules,
                       frame_ids=["f-1"], needs_judgement=True)


def test_judge_uses_model(monkeypatch):
    monkeypatch.setattr(judge, "gemma_json", lambda *a, **k: {"stuck": False, "reason": "steady typing"})
    assert judge.judge_stuck(_sig(["R1_time"]), []) == (False, "steady typing")


def test_judge_fallback_when_model_down(monkeypatch):
    def boom(*a, **k):
        raise LLMError("offline")
    monkeypatch.setattr(judge, "gemma_json", boom)
    assert judge.judge_stuck(_sig(["R1_time"]), [])[0] is False
    assert judge.judge_stuck(_sig(["R1_time", "R2_loop"]), [])[0] is True


def test_tag_topics(monkeypatch):
    topics._cache.clear()
    monkeypatch.setattr(topics, "gemma_json", lambda *a, **k: {"topics": ["dynamic-programming", "arrays"]})
    assert topics.tag_topics("Coin Change", "leetcode") == ["dynamic-programming", "arrays"]
    assert topics.tag_topics(None, "leetcode") == ["other"]


def test_draft_report_claims(monkeypatch):
    monkeypatch.setattr(report_draft, "gemma_json", lambda *a, **k: {"claims": [{
        "kind": "weakness", "text": "DP took 34.3 minutes on average.", "topic": "dynamic-programming",
        "numeric_claims": {"avg_active_min": 34.3}, "about_problems": ["leetcode:coin-change"],
        "confidence": "speculative"}]})
    [c] = report_draft.draft_report_claims({"topics": {}})
    assert c.id.startswith("clm-") and c.gate_status == "unchecked"
    assert c.numeric_claims == {"avg_active_min": 34.3}
