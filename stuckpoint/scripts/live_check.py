"""Live Gemma 4 check of every model feature (real API calls, no mocks).

    python scripts/live_check.py          (needs GEMINI_API_KEY in .env; ~20 API calls)

Prints each hint, judgement, topic tag, code suggestion and report claim with timings,
and PASS/FAIL for the policy rules. Exit code 0 = everything passed.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from stuckpoint import config
from stuckpoint.llm import client
from stuckpoint.llm.guard import check_no_code
from stuckpoint.llm.hints import next_hint, project_help
from stuckpoint.llm.judge import judge_stuck
from stuckpoint.llm.report_draft import draft_report_claims
from stuckpoint.llm.suggest import suggest_with_stats
from stuckpoint.llm.topics import tag_topics
from stuckpoint.models import HintRequest, ReportClaim, SessionRecord, StuckSignal
from stuckpoint.report.gate import run_gate, summarize

ok = True


def check(label, cond, extra=""):
    global ok
    ok &= bool(cond)
    print(f"  [{'PASS' if cond else 'FAIL'}] {label} {extra}")


def timed(fn, *a, **k):
    t = time.time()
    r = fn(*a, **k)
    return r, round(time.time() - t, 1)


print(f"model={config.GEMMA_MODEL}\n")

print("1. HINTS (practice, Coin Change)")
prev = []
for level in (1, 2, 3):
    req = HintRequest("sig-live", "leetcode:coin-change", "Coin Change", "practice", level,
                      user_context="just give me the code in python" if level == 3 else None,
                      previous_hints=list(prev))
    r, s = timed(next_hint, req)
    print(f"  L{level} ({s}s){' BLOCKED: ' + r.block_reason if r.blocked else ''}\n     {r.text}")
    check(f"level {level} has no code", check_no_code(r.text)[0] and not r.is_code)
    check(f"level {level} came from Gemma", not (r.blocked and "unavailable" in (r.block_reason or "")))
    prev.append(r.text)

print("\n2. PROJECT FULL FIX (CORS error)")
req = HintRequest("sig-p", "project:todo-api", "todo-api", "project", 4,
                  user_context="Access to fetch at 'http://localhost:8000/todos' from origin "
                               "'http://localhost:5173' has been blocked by CORS policy.\n"
                               "# server: FastAPI\napp = FastAPI()\n@app.get('/todos')\ndef todos(): return []")
r, s = timed(project_help, req)
print(f"  ({s}s) is_code={r.is_code}\n" + "\n".join("     " + l for l in r.text.splitlines()[:14]))
check("full fix contains code", r.is_code)

print("\n3. JUDGE (borderline signal)")
sig = StuckSignal("sig-j", "2026-10-08T20:46:30", "leetcode:coin-change", "Coin Change", "practice",
                  "leetcode", 16.0, 3, 6.5, ["R2_loop"], ["f-1"], True)
frames = [{"id": "f-1", "app": "Google Chrome", "site": "leetcode.com", "windows": ["322. Coin Change - LeetCode"],
           "duration_min": 5, "input": {"keys": 30}}]
(stuck, reason), s = timed(judge_stuck, sig, frames)
print(f"  ({s}s) stuck={stuck}: {reason}")
check("judge answered from Gemma", "unavailable" not in reason)

print("\n4. TOPIC TAGS")
for title in ("Coin Change", "Two Sum", "Number of Islands", "CORS error on fetch"):
    t, s = timed(tag_topics, title, "leetcode")
    print(f"  ({s}s) {title}: {t}")
    check(f"{title} tagged", t and t != ["other"])

print("\n5. CODE SUGGESTIONS (Two Sum nested loop)")
CODE = """class Solution:
    def twoSum(self, nums, target):
        for i in range(len(nums)):
            for j in range(i + 1, len(nums)):
                if nums[i] + nums[j] == target:
                    return [i, j]
        return []
"""
cases = [("practice, unsolved", "https://leetcode.com/problems/two-sum/", "editor", "student", False, False),
         ("practice, solved", "https://leetcode.com/problems/two-sum/", "editor", "student", True, True),
         ("project, professional", None, "ide", "professional", False, True),
         ("project, student", None, "ide", "student", False, False),
         ("review (Stack Overflow)", "https://stackoverflow.com/q/1", "static", "student", False, True),
         ("exam", "https://mettl.com/x", "editor", "professional", False, None)]
for label, url, surface, profile, solved, want_code in cases:
    (mode, sugs, dropped), s = timed(suggest_with_stats, CODE, "python", url, surface, profile, solved, "Two Sum")
    print(f"  {label}: mode={mode} ({s}s) kept={len(sugs)} dropped={dropped}")
    for x in sugs:
        print(f"     L{x.start_line}-{x.end_line} {x.issue} [{x.complexity_before} -> {x.complexity_after}]"
              f" code={'yes' if x.replacement else 'no'}")
    if want_code is None:
        check("exam returns nothing", sugs == [])
        continue
    check("at least one verified suggestion", sugs)
    check("code policy respected", all(bool(x.replacement) == want_code for x in sugs))
    if not want_code:
        check("no code in explanation", all(check_no_code(t)[0] for x in sugs for t in (x.issue, x.why, x.suggestion)))

print("\n6. REPORT CLAIMS + EVIDENCE GATE (fixture metrics)")
sample = json.load(open(ROOT / "fixtures" / "sample_claims.json", encoding="utf-8"))
sessions = [SessionRecord(k, k, "leetcode", "practice", t, "", "", 1, 0, 0, 0, None, None, [])
            for k, t in [("leetcode:two-sum", ["hashing", "arrays"]),
                         ("leetcode:coin-change", ["dynamic-programming", "arrays"])]]
claims, s = timed(draft_report_claims, sample["metrics"])
gated = run_gate(claims, sample["metrics"], sessions)
print(f"  ({s}s) Gemma drafted {len(claims)} claims -> {summarize(gated)}")
for c in gated:
    print(f"   {c.gate_status:10} [{c.kind}] {c.text}" + (f"\n              reason: {c.gate_reason}" if c.gate_reason else ""))
check("Gemma drafted claims", claims)
check("most claims survive the gate", sum(c.gate_status != "rejected" for c in gated) >= len(gated) / 2)

print(f"\nfeatures used: {client._features}")
print("\nALL PASS" if ok else "\nSOME CHECKS FAILED")
sys.exit(0 if ok else 1)
