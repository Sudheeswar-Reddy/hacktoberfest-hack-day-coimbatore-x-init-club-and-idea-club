from datetime import datetime

from stuckpoint.detector.stuck import detect, parse_clock
from stuckpoint.models import StuckSignal

NOW = datetime(2026, 10, 8, 20, 46, 30)
_counter = iter(range(1, 10_000))


def f(start, end, site="leetcode.com", window="322. Coin Change - LeetCode",
      keys=40, pages=None, app="Google Chrome"):
    fmt = "%H:%M:%S"
    dur = (datetime.strptime(end, fmt) - datetime.strptime(start, fmt)).seconds / 60
    fr = {"id": f"f-{next(_counter):04d}", "app": app, "site": site, "start": start, "end": end,
          "duration_min": round(dur, 1), "windows": [window],
          "input": {"keys": keys}, "evidence": {"frame_ids": "1..9"}}
    if pages:
        fr["pages"] = pages
    return fr


SO = dict(site="stackoverflow.com", window="Coin change - Stack Overflow", pages=[{"kind": "question"}])
GPT = dict(site="chatgpt.com", window="ChatGPT", pages=[{"kind": "ai_chat"}])


def stuck_session():
    return [
        f("20:12:00", "20:20:00", keys=50),
        f("20:20:00", "20:24:00", **SO),
        f("20:24:00", "20:29:00", keys=35),
        f("20:29:00", "20:33:00", **GPT),
        f("20:33:00", "20:38:00", keys=40),
        f("20:38:00", "20:41:00", **SO),
        f("20:41:00", "20:46:30", keys=30),
    ]


def test_clearly_stuck_is_confident():
    [sig] = detect(stuck_session(), NOW)
    assert sig.problem_key == "leetcode:coin-change"
    assert sig.loops == 3
    assert set(sig.rules_fired) == {"R1_time", "R2_loop", "R3_low_input"}
    assert sig.needs_judgement is False
    assert sig.minutes_on_problem >= 30


def test_productive_work_is_not_stuck():
    frames = [f("20:30:00", "20:46:30", keys=900)]   # 16.5 min, ~55 keys/min, no loops
    sigs = detect(frames, NOW)
    # R1 fires on time alone -> only a borderline signal for Gemma, never a confident one
    assert all(s.needs_judgement for s in sigs)


def test_short_session_no_signal():
    assert detect([f("20:40:00", "20:46:30", keys=300)], NOW) == []


def test_borderline_needs_judgement():
    # 12 minutes total (< 15, so no R1), steady typing, but 3 help loops
    frames = [
        f("20:28:00", "20:30:00", keys=80),
        f("20:30:00", "20:32:00", **SO),
        f("20:32:00", "20:34:00", keys=70),
        f("20:34:00", "20:36:00", **GPT),
        f("20:36:00", "20:38:00", keys=60),
        f("20:38:00", "20:39:00", **SO),
        f("20:39:00", "20:40:00", keys=40),
    ]
    now = datetime(2026, 10, 8, 20, 40, 0)
    [sig] = detect(frames, now)
    assert sig.rules_fired == ["R2_loop"]
    assert sig.needs_judgement is True


def test_exam_site_never_signals():
    frames = stuck_session() + [f("20:46:30", "20:47:00", site="mettl.com", window="Exam")]
    assert detect(frames, datetime(2026, 10, 8, 20, 47, 0)) == []


def test_project_with_localhost_attributed():
    frames = [
        f("20:20:00", "20:30:00", app="Code", site=None, window="app.py — todo-api", keys=60),
        f("20:30:00", "20:32:00", site="localhost", window="Todo", pages=[{"kind": "local_dev"}], keys=0),
        f("20:32:00", "20:35:00", **SO),
        f("20:35:00", "20:40:00", app="Code", site=None, window="app.py — todo-api", keys=20),
        f("20:40:00", "20:43:00", **GPT),
        f("20:43:00", "20:46:30", app="Code", site=None, window="app.py — todo-api", keys=10),
    ]
    [sig] = detect(frames, NOW)
    assert sig.mode == "project" and sig.problem_key == "project:todo-api"
    assert "R1_time" in sig.rules_fired


class _Store:
    def __init__(self, sig):
        self.sig = sig

    def last_signal_for(self, key):
        return self.sig


def _prev(status, minutes_ago):
    created = NOW.replace(minute=NOW.minute - minutes_ago).isoformat()
    return StuckSignal(id="sig-old", created_at=created, problem_key="leetcode:coin-change",
                       problem_title="Coin Change", mode="practice", platform="leetcode",
                       minutes_on_problem=20, loops=2, keys_per_min=5, rules_fired=["R1_time"],
                       frame_ids=[], needs_judgement=False, status=status)


def test_cooldown_and_snooze():
    frames = stuck_session()
    assert detect(frames, NOW, store=_Store(_prev("dismissed", 5))) == []      # in cooldown
    assert len(detect(frames, NOW, store=_Store(_prev("dismissed", 12)))) == 1  # cooldown over
    assert detect(frames, NOW, store=_Store(_prev("snoozed", 12))) == []       # still snoozed


def test_parse_clock_midnight_wrap():
    now = datetime(2026, 10, 9, 0, 5, 0)
    assert parse_clock("23:55:00", now) == datetime(2026, 10, 8, 23, 55, 0)
