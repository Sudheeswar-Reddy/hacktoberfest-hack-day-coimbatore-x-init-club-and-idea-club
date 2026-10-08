import pytest

from stuckpoint.llm import suggest as sg
from stuckpoint.llm.guard import check_no_code

CODE = """class Solution:
    def twoSum(self, nums, target):
        for i in range(len(nums)):

            for j in range(i + 1, len(nums)):
                if nums[i] + nums[j] == target:
                    return [i, j]
        return []
"""

NESTED = {
    "quote": "for i in range(len(nums)):\n    for j in range(i + 1, len(nums)):",
    "issue": "Nested loop over the same array",
    "why": "Every element re-scans the rest of the array.",
    "complexity_before": "O(n^2)", "complexity_after": "O(n)",
    "suggestion": "Remember each number's index in a hash map and look up the complement.",
    "replacement": "seen = {}\nfor i, x in enumerate(nums):\n    if target - x in seen:\n        return [seen[target - x], i]\n    seen[x] = i",
    "confidence": "high",
}
FAKE = {**NESTED, "quote": "for k in sorted(nums):", "issue": "Hallucinated"}

LEETCODE = "https://leetcode.com/problems/two-sum/"
SANDBOX = "https://codesandbox.io/p/sandbox/todo-app"
SO = "https://stackoverflow.com/questions/1/two-sum"
EXAM = "https://tests.mettl.com/attempt/123"


@pytest.fixture(autouse=True)
def _fresh_cache():
    sg._cache.clear()


def _mock(monkeypatch, *items):
    calls = []

    def fake(prompt, schema, **kw):
        calls.append(prompt)
        return {"suggestions": [dict(i) for i in items]}
    monkeypatch.setattr(sg, "gemma_json", fake)
    return calls


def _no_code_anywhere(s):
    assert s.replacement is None
    for text in (s.issue, s.why, s.suggestion):
        assert check_no_code(text)[0], text


# ---- quote verification --------------------------------------------------------
def test_locate_ignores_whitespace_and_blank_lines():
    assert sg.locate(CODE, NESTED["quote"]) == (3, 5)
    assert sg.locate(CODE, "return [i, j]") == (7, 7)
    assert sg.locate(CODE, "x = 1") is None


def test_locate_falls_back_to_first_two_lines():
    quote = NESTED["quote"] + "\n        if nums[i] * nums[j] == target:"   # 3rd line misquoted
    assert sg.locate(CODE, quote) == (3, 6)


def test_quote_found_lines_computed_by_us(monkeypatch):
    _mock(monkeypatch, NESTED)
    mode, [s] = sg.suggest(CODE, "python", SANDBOX, "editor")
    assert mode == "project" and (s.start_line, s.end_line) == (3, 5)
    assert "for j in range" in s.quote


def test_hallucinated_quote_dropped(monkeypatch):
    _mock(monkeypatch, NESTED, FAKE)
    _, sugs, dropped = sg.suggest_with_stats(CODE, "python", SANDBOX, "editor")
    assert [s.issue for s in sugs] == [NESTED["issue"]] and dropped == 1


# ---- the Part 3.3 policy table ---------------------------------------------------
def test_practice_unsolved_never_has_code(monkeypatch):
    leaky = {**NESTED, "why": "Use `seen[x] = i` instead.", "suggestion": "dp[i] = min(dp[i], 1)"}
    calls = _mock(monkeypatch, leaky)
    for profile in ("professional", "student"):
        mode, [s] = sg.suggest(CODE, "python", LEETCODE, "editor", profile, solved=False)
        assert mode == "practice"
        _no_code_anywhere(s)
    assert "always null" in calls[0]


def test_practice_solved_keeps_code(monkeypatch):
    _mock(monkeypatch, NESTED)
    _, [s] = sg.suggest(CODE, "python", LEETCODE, "editor", "student", solved=True)
    assert s.replacement and "seen" in s.replacement


def test_student_project_unsolved_no_code(monkeypatch):
    _mock(monkeypatch, {**NESTED, "suggestion": "for x in nums: seen[x] = 1"})
    mode, [s] = sg.suggest(CODE, "python", SANDBOX, "editor", "student", solved=False)
    assert mode == "project"
    _no_code_anywhere(s)


def test_student_project_show_me_gives_code(monkeypatch):
    _mock(monkeypatch, NESTED)
    _, [s] = sg.suggest(CODE, "python", None, "ide", "student", solved=True)
    assert s.replacement


def test_professional_project_keeps_code(monkeypatch):
    _mock(monkeypatch, NESTED)
    mode, [s] = sg.suggest(CODE, "python", None, "ide", "professional")
    assert mode == "project" and s.replacement


@pytest.mark.parametrize("profile", ["professional", "student"])
def test_review_keeps_code(monkeypatch, profile):
    _mock(monkeypatch, NESTED)
    mode, [s] = sg.suggest(CODE, "python", SO, "static", profile)
    assert mode == "review" and s.replacement


def test_exam_gets_nothing(monkeypatch):
    calls = _mock(monkeypatch, NESTED)
    assert sg.suggest(CODE, "python", EXAM, "editor") == ("exam", [])
    assert sg.suggest(CODE, "python", EXAM, "static") == ("exam", [])
    assert calls == []


def test_static_block_on_practice_site_is_practice(monkeypatch):
    _mock(monkeypatch, NESTED)
    mode, [s] = sg.suggest(CODE, "python", LEETCODE, "static")
    assert mode == "practice" and s.replacement is None


@pytest.mark.parametrize("mode,profile,solved,allowed", [
    ("practice", "professional", False, False), ("practice", "student", True, True),
    ("project", "professional", False, True), ("project", "student", False, False),
    ("project", "student", True, True), ("review", "student", False, True),
    ("exam", "professional", True, False), ("other", "professional", True, False),
])
def test_code_allowed_table(mode, profile, solved, allowed):
    assert sg.code_allowed(mode, profile, solved) is allowed


# ---- caching, language, failure ---------------------------------------------------
def test_cached_by_code_mode_profile_solved(monkeypatch):
    calls = _mock(monkeypatch, NESTED)
    sg.suggest(CODE, "python", LEETCODE, "editor")
    sg.suggest(CODE, "python", LEETCODE, "editor")                    # cache hit
    sg.suggest(CODE, "python", LEETCODE, "editor", solved=True)       # different policy
    sg.suggest(CODE, "python", SANDBOX, "editor", "student")          # different mode/profile
    assert len(calls) == 3


def test_unknown_language_is_inferred(monkeypatch):
    calls = _mock(monkeypatch, NESTED)
    sg.suggest(CODE, "", None, "ide")
    assert "infer it from the code" in calls[0]


def test_model_down_returns_empty(monkeypatch):
    def boom(*a, **k):
        raise sg.LLMError("offline")
    monkeypatch.setattr(sg, "gemma_json", boom)
    assert sg.suggest(CODE, "python", None, "ide") == ("project", [])


def test_card_markdown():
    s = sg.CodeSuggestion(id="s", start_line=1, end_line=2, quote="q", issue="Nested loop", why="Slow.",
                          complexity_before="O(n^2)", complexity_after="O(n)",
                          suggestion="Use a map.", replacement="m = {}", confidence="high")
    md = sg.card_markdown(s, "python")
    assert "O(n^2) → O(n)" in md and "```python\nm = {}\n```" in md
