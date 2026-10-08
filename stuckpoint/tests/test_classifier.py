import json
from pathlib import Path

import pytest

from stuckpoint.context.classifier import classify, clean_title, is_help, mode_for

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample_frames.json"


def frame(app="Google Chrome", site=None, window="", pages=None):
    f = {"id": "f-x", "app": app, "start": "10:00:00", "end": "10:05:00",
         "duration_min": 5.0, "windows": [window], "evidence": {"frame_ids": "1..2"}}
    if site:
        f["site"] = site
    if pages:
        f["pages"] = pages
    return f


@pytest.mark.parametrize("window,expected", [
    ("322. Coin Change - LeetCode", "Coin Change"),
    ("322. Coin Change - LeetCode - Google Chrome", "Coin Change"),
    ("Two Sum - Submissions - LeetCode", "Two Sum"),
    ("(2) Valid Parentheses - LeetCode", "Valid Parentheses"),
    ("Diagonal Difference | HackerRank", "Diagonal Difference"),
])
def test_clean_title(window, expected):
    assert clean_title(window) == expected


def test_leetcode_is_practice_with_problem_key():
    lab = classify(frame(site="leetcode.com", window="322. Coin Change - LeetCode"))
    assert (lab.mode, lab.platform, lab.problem_key, lab.problem_title) == \
        ("practice", "leetcode", "leetcode:coin-change", "Coin Change")


def test_leetcode_list_page_has_no_problem():
    lab = classify(frame(site="leetcode.com", window="Problems - LeetCode"))
    assert lab.mode == "practice" and lab.problem_key is None


def test_exam_site():
    assert classify(frame(site="tests.mettl.com", window="Assessment")).mode == "exam"


@pytest.mark.parametrize("window", [
    "app.py — todo-api — Visual Studio Code",   # Windows / Linux
    "app.py — todo-api",                        # macOS
])
def test_vscode_project(window):
    lab = classify(frame(app="Code", window=window))
    assert lab.mode == "project" and lab.problem_key == "project:todo-api"


def test_localhost_is_unnamed_project():
    lab = classify(frame(site="localhost", window="Todo API", pages=[{"kind": "local_dev"}]))
    assert lab.mode == "project" and lab.problem_key is None


def test_help_detection():
    assert is_help(frame(site="stackoverflow.com", pages=[{"kind": "question"}]))
    assert is_help(frame(site="chatgpt.com", pages=[{"kind": "ai_chat"}]))
    assert is_help(frame(site="google.com", pages=[{"kind": "search", "entity": "dp"}]))
    assert not is_help(frame(site="docs.google.com", pages=[{"kind": "doc"}]))
    assert not is_help(frame(site="leetcode.com", window="Coin Change - LeetCode"))


def test_fixture_classifies():
    frames = json.loads(FIXTURE.read_text())["frames"]
    modes = [classify(f).mode for f in frames]
    assert modes.count("practice") == 6
    assert "project" in modes


@pytest.mark.parametrize("url,surface,mode", [
    ("https://leetcode.com/problems/two-sum/", "editor", "practice"),
    ("https://www.hackerrank.com/challenges/x", "static", "practice"),
    ("https://tests.mettl.com/attempt/1", "editor", "exam"),
    ("https://codesandbox.io/p/sandbox/x", "editor", "project"),
    ("https://some-random-site.dev/playground", "editor", "project"),
    (None, "ide", "project"),
    ("https://stackoverflow.com/questions/1", "static", "review"),
    ("https://github.com/a/b/blob/main/x.py", "static", "review"),
    ("https://chatgpt.com/c/1", "static", "review"),
    ("https://example.com", None, "other"),
])
def test_mode_for(url, surface, mode):
    assert mode_for(url, surface) == mode


@pytest.mark.parametrize("site,window,key", [
    ("codesandbox.io", "todo-app - CodeSandbox", "project:todo-app"),
    ("replit.com", "my-repl - Replit", "project:my-repl"),
    ("colab.research.google.com", "analysis.ipynb - Colab", "project:analysis-ipynb"),
    ("vscode.dev", "app.py — todo-api — Visual Studio Code", "project:todo-api"),
])
def test_online_editors_are_projects(site, window, key):
    lab = classify(frame(site=site, window=window))
    assert lab.mode == "project" and lab.problem_key == key
