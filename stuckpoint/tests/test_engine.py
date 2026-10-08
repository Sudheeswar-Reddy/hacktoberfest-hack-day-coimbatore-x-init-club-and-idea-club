"""Engine end to end, the way the extensions use it: events -> Activity Frames ->
detector -> /status -> hints / suggestions / report. Gemma is mocked."""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from stuckpoint import config, server
from stuckpoint.ingest import ingest, to_capture_ts
from stuckpoint.llm import hints, report_draft, suggest, topics

LC = ("322. Coin Change - LeetCode", "https://leetcode.com/problems/coin-change/description/")
SO = ("Coin change minimum coins - Stack Overflow", "https://stackoverflow.com/questions/1/coin-change")
GPT = ("ChatGPT", "https://chatgpt.com/c/abc")
GOOGLE = ("coin change dp - Google Search", "https://www.google.com/search?q=coin+change+dp")


def chrome_session(script):
    """What tracker.js sends: a focus heartbeat + an input count every 10 s."""
    total = sum(m for _, m, _ in script)
    t = datetime.now(timezone.utc) - timedelta(minutes=total)
    events, owed = [], 0.0
    for (title, url), minutes, kpm in script:
        for _ in range(int(minutes * 6)):
            ts = t.isoformat().replace("+00:00", "Z")
            owed += kpm / 6
            keys, owed = int(owed), owed - int(owed)
            events.append({"type": "focus", "ts": ts, "app": "Google Chrome", "title": title, "url": url})
            events.append({"type": "input", "ts": ts, "app": "Google Chrome", "keys": keys, "clicks": 1})
            t += timedelta(seconds=10)
    return events


STUCK = [(LC, 6, 5), (SO, 3, 1), (LC, 4, 6), (GPT, 3, 12), (LC, 3, 4), (GOOGLE, 2, 6), (LC, 2, 3)]


@pytest.fixture
def client(monkeypatch):
    server._store = None
    server._status_cache.update(at=0.0, context=None)
    monkeypatch.setattr(topics, "gemma_json", lambda *a, **k: {"topics": ["dynamic-programming"]})
    topics._cache.clear()
    return TestClient(server.app)          # no `with`: the background loop stays off


def test_capture_ts_format():
    assert to_capture_ts("2026-10-08T07:43:10.123Z") == "2026-10-08T07:43:10"
    assert to_capture_ts("garbage") is None


def test_ingest_stores_counts_not_text():
    n = ingest([{"type": "input", "ts": "2026-10-08T07:43:10Z", "keys": 23, "clicks": 2},
                {"type": "focus", "ts": "2026-10-08T07:43:10Z", "title": "New Tab", "url": "chrome://newtab/"},
                {"type": "focus", "ts": "bad"}, "junk"], "chrome")
    assert n == 3                                   # 1 text row + 2 clicks; chrome:// skipped
    conn = sqlite3.connect(config.AFRAMES_DB)
    [(text,)] = conn.execute("SELECT text_content FROM ui_events WHERE event_type='text'").fetchall()
    assert text == "x" * 23 and conn.execute("SELECT COUNT(*) FROM frames").fetchone()[0] == 0


def test_health_and_empty_status(client):
    assert client.get("/health").json()["ok"] is True
    assert client.get("/status").json() == {"context": None, "signal": None}
    assert client.post("/check").json()["ok"] is False


def test_stuck_flow_end_to_end(client, monkeypatch):
    r = client.post("/events", json={"source": "chrome", "events": chrome_session(STUCK)})
    assert r.json()["stored"] > 200

    frames = client.get("/frames").json()["frames"]
    assert {f["context"]["mode"] for f in frames} == {"practice", "other"}

    [sig] = client.post("/check").json()["signals"]
    assert sig["status"] == "confirmed" and sig["problem_key"] == "leetcode:coin-change"
    assert sig["loops"] == 3 and "R2_loop" in sig["rules_fired"]

    st = client.get("/status").json()
    assert st["signal"]["id"] == sig["id"]
    assert st["context"]["mode"] == "practice" and st["context"]["problem_title"] == "Coin Change"

    assert client.post(f"/signal/{sig['id']}/status", json={"status": "offered"}).json()["ok"]
    assert client.post("/signal/sig-nope/status", json={"status": "offered"}).status_code == 404

    seen = []
    monkeypatch.setattr(hints, "gemma_json", lambda prompt, *a, **k:
                        seen.append(prompt) or {"level": 1, "text": f"Hint number {len(seen)}."})
    body = {"signal_id": sig["id"], "problem_key": sig["problem_key"],
            "problem_title": "Coin Change", "mode": "practice"}
    h1 = client.post("/hint", json=body).json()
    h2 = client.post("/hint", json=body).json()
    assert (h1["level"], h2["level"]) == (1, 2)        # level advances from stored hints
    assert "Hint number 1." in seen[1]                 # previous hints are passed on
    assert client.get("/status").json()["signal"]["status"] == "accepted"

    assert client.post("/help/full", json={**body, "level": 4}).status_code == 403

    assert client.post("/solved", json={"problem_key": sig["problem_key"]}).json()["ok"]

    monkeypatch.setattr(report_draft, "gemma_json", lambda *a, **k: {"claims": [
        {"kind": "weakness", "text": "Dynamic programming needed 2 hints.", "topic": "dynamic-programming",
         "numeric_claims": {"hints_used": 2}, "about_problems": ["leetcode:coin-change"],
         "confidence": "medium"},
        {"kind": "weakness", "text": "You spent 99 minutes on DP.", "topic": "dynamic-programming",
         "numeric_claims": {"avg_active_min": 99}, "about_problems": ["leetcode:coin-change"],
         "confidence": "medium"}]})
    rep = client.get("/report").json()
    dp = rep["metrics"]["topics"]["dynamic-programming"]
    assert dp["problems"] == 1 and dp["hints_used"] == 2 and dp["stuck_episodes"] == 1 and dp["solved"] == 1
    assert rep["gate_summary"] == {"total": 2, "passed": 0, "downgraded": 1, "rejected": 1}
    [s] = rep["sessions"]
    assert s["solved"] is True and s["max_hint_level"] == 2


def test_snooze_hides_signal(client):
    client.post("/events", json={"events": chrome_session(STUCK)})
    [sig] = client.post("/check").json()["signals"]
    client.post(f"/signal/{sig['id']}/status", json={"status": "snoozed"})
    assert client.get("/status").json()["signal"] is None
    assert client.post("/check").json()["signals"] == []      # no new signal while snoozed


def test_vscode_events_are_project(client):
    t = datetime.now(timezone.utc) - timedelta(minutes=5)
    ev = [{"type": "focus", "ts": (t + timedelta(seconds=10 * i)).isoformat(), "app": "Code",
           "title": "app.py — todo-api", "url": None} for i in range(30)]
    client.post("/events", json={"source": "vscode", "events": ev})
    ctx = client.get("/status").json()["context"]
    assert ctx["mode"] == "project" and ctx["problem_key"] == "project:todo-api"


def test_suggest_route_policy(client, monkeypatch):
    suggest._cache.clear()
    monkeypatch.setattr(suggest, "gemma_json", lambda *a, **k: {"suggestions": [
        {"quote": "for j in range(n):", "issue": "Nested loop", "why": "Re-scans.",
         "complexity_before": "O(n^2)", "complexity_after": "O(n)",
         "suggestion": "Use a hash map.", "replacement": "seen = {}", "confidence": "high"},
        {"quote": "not in the code", "issue": "x", "why": "", "suggestion": "y", "confidence": "low"
         if False else "speculative"}]})
    code = "n = len(a)\nfor i in range(n):\n    for j in range(n):\n        pass\n"
    lc = "https://leetcode.com/problems/two-sum/"
    r = client.post("/suggest", json={"code": code, "url": lc, "surface": "editor"}).json()
    assert r["mode"] == "practice" and r["dropped"] == 1 and r["code_allowed"] is False
    [s] = r["suggestions"]
    assert (s["start_line"], s["end_line"]) == (3, 3) and s["replacement"] is None

    r = client.post("/suggest", json={"code": code, "url": lc, "surface": "editor", "solved": True}).json()
    assert r["suggestions"][0]["replacement"] == "seen = {}"

    r = client.post("/suggest", json={"code": code, "language": "python", "url": None, "surface": "ide"}).json()
    assert r["mode"] == "project" and r["suggestions"][0]["replacement"] == "seen = {}"

    r = client.post("/suggest", json={"code": code, "surface": "ide", "profile": "student"}).json()
    assert r["suggestions"][0]["replacement"] is None

    r = client.post("/suggest", json={"code": code, "url": "https://stackoverflow.com/q/1",
                                      "surface": "static", "profile": "student"}).json()
    assert r["mode"] == "review" and r["suggestions"][0]["replacement"] == "seen = {}"

    r = client.post("/suggest", json={"code": code, "url": "https://mettl.com/x", "surface": "editor"}).json()
    assert r == {"mode": "exam", "suggestions": [], "dropped": 0, "code_allowed": False}
    assert client.post("/suggest", json={"code": code, "surface": "nope"}).status_code == 422


def test_fixture_mode_report(client, monkeypatch):
    monkeypatch.setattr(config, "SOURCE", "fixture")
    monkeypatch.setattr(report_draft, "gemma_json", lambda *a, **k: (_ for _ in ()).throw(
        report_draft.LLMError("offline")))
    rep = client.get("/report").json()
    assert rep["metrics"]["overall"]["problems"] == 3          # two-sum, coin-change, todo-api
    assert rep["claims"] == [] and rep["llm_available"] is False
