"""Recorder -> unmodified activity_frames compiler -> classifier/detector, end to end."""
import sys
from datetime import datetime, timedelta, timezone

import pytest

from stuckpoint.capture.backends.common import app_name, normalize_url, url_from_title
from stuckpoint.capture.recorder import Focus, Recorder
from stuckpoint.context.classifier import classify, clean_title
from stuckpoint.detector.stuck import detect

LC = Focus("Google Chrome", "322. Coin Change - LeetCode - Google Chrome",
           "https://leetcode.com/problems/coin-change/description/", "browser")
SO = Focus("Google Chrome", "Coin change minimum coins - Stack Overflow - Google Chrome",
           "https://stackoverflow.com/questions/123/coin-change", "browser")
GPT = Focus("Google Chrome", "ChatGPT - Google Chrome", "https://chatgpt.com/c/abc", "browser")
GOOGLE = Focus("Google Chrome", "coin change dp - Google Search - Google Chrome",
               "https://www.google.com/search?q=coin+change+dp", "browser")
VSCODE = Focus("Code", "app.py - todo-api - Visual Studio Code")


class FakeBackend:
    def __init__(self):
        self.focus = None

    def foreground(self):
        return self.focus

    def idle_seconds(self):
        return 0.0

    def start_input(self, cb):
        pass

    def stop_input(self):
        pass


class Clock:
    def __init__(self, start):
        self.t = start

    def __call__(self):
        return self.t


def _record(tmp_path, script):
    """script: [(focus, minutes, keys_per_min)] played back ending ~now."""
    total = sum(m for _, m, _ in script)
    clock = Clock(datetime.now(timezone.utc) - timedelta(minutes=total))
    backend = FakeBackend()
    db = str(tmp_path / "capture.sqlite")
    rec = Recorder(db, backend, heartbeat_s=10, clock=clock)
    owed = 0.0
    for focus, minutes, kpm in script:
        backend.focus = focus
        for _ in range(int(minutes * 6)):          # one tick every 10 s
            owed += kpm / 6
            while owed >= 1:
                rec.on_input("key")
                owed -= 1
            rec.tick()
            clock.t += timedelta(seconds=10)
    rec.conn.close()
    return db


def _compile(db):
    from activity_frames import ActivityLog

    log = ActivityLog(db, min_minutes=0)
    try:
        return log.recent(hours=1).to_dict()["frames"]
    finally:
        log.close()


def test_stuck_session_end_to_end(tmp_path):
    db = _record(tmp_path, [(LC, 6, 5), (SO, 3, 1), (LC, 4, 6), (GPT, 3, 12),
                            (LC, 3, 4), (GOOGLE, 2, 6), (LC, 2, 3)])
    frames = _compile(db)
    kinds = [(f.get("site"), [p["kind"] for p in f.get("pages", [])]) for f in frames]
    assert ("stackoverflow.com", ["question"]) in kinds
    assert ("chatgpt.com", ["ai_chat"]) in kinds
    assert ("google.com", ["search"]) in kinds
    assert classify(frames[0]).problem_key == "leetcode:coin-change"
    assert frames[0]["input"]["keys"] > 0

    [sig] = detect(frames, datetime.now().replace(microsecond=0))
    assert sig.problem_key == "leetcode:coin-change"
    assert sig.loops == 3
    assert "R1_time" in sig.rules_fired and "R2_loop" in sig.rules_fired
    assert sig.needs_judgement is False


def test_productive_project_not_confident(tmp_path):
    db = _record(tmp_path, [(VSCODE, 18, 60)])
    frames = _compile(db)
    lab = classify(frames[0])
    assert (lab.mode, lab.problem_key) == ("project", "project:todo-api")
    assert all(s.needs_judgement for s in detect(frames, datetime.now().replace(microsecond=0)))


def test_key_events_carry_no_content(tmp_path):
    import sqlite3

    db = _record(tmp_path, [(LC, 1, 30)])
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM ui_events WHERE text_content IS NOT NULL").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM ui_events WHERE event_type='key'").fetchone()[0] > 0


@pytest.mark.parametrize("title,url", [
    ("322. Coin Change - LeetCode - Google Chrome", "https://leetcode.com/problems/coin-change/"),
    ("Two Sum - Submissions - LeetCode", "https://leetcode.com/problems/two-sum/"),
    ("dp tutorial - Google Search - Google Chrome", "https://www.google.com/search?q=dp%20tutorial"),
    ("python - Why? - Stack Overflow - Google Chrome", "https://stackoverflow.com/"),
    ("Notes - Google Docs", None),
])
def test_url_from_title(title, url):
    assert url_from_title(title) == url


def test_title_fallback_classifies_as_practice():
    url = url_from_title("322. Coin Change - LeetCode - Google Chrome")
    from activity_frames import parse_url

    assert parse_url(url).domain == "leetcode.com"


@pytest.mark.parametrize("raw,url", [
    ("leetcode.com/problems/coin-change/", "https://leetcode.com/problems/coin-change/"),
    ("localhost:5173/todos", "http://localhost:5173/todos"),
    ("https://chatgpt.com/", "https://chatgpt.com/"),
    ("how to do dp", None),
    ("", None),
])
def test_normalize_url(raw, url):
    assert normalize_url(raw) == url


def test_app_names():
    assert app_name("chrome.exe") == "Google Chrome"
    assert app_name("Code.exe") == "Code"
    assert app_name("WindowsTerminal.exe") == "Windows Terminal"
    assert app_name("SomethingElse.exe") == "SomethingElse"


def test_windows_titles_clean():
    assert clean_title("Coin Change - LeetCode and 2 more pages - Personal - Microsoft​ Edge") \
        == "Coin Change"
    lab = classify({"id": "f-1", "app": "Windows Terminal", "start": "10:00:00", "end": "10:01:00",
                    "duration_min": 1, "windows": ["PowerShell"]})
    assert lab.mode == "project"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows backend")
def test_windows_backend_smoke():
    from stuckpoint.capture.backends.windows import WindowsBackend

    b = WindowsBackend()
    f = b.foreground()
    assert f is None or isinstance(f, Focus)
    assert b.idle_seconds() >= 0
