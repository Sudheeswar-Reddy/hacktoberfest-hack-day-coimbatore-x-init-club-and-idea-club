"""Shared data contracts (instructions.md, Part 3.2).

FROZEN after 11:45 — change only after telling all four teammates.
Every model has to_dict()/from_dict() so the store can save it as JSON.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Literal, Optional

Mode = Literal["practice", "project", "review", "exam", "other"]   # review: read-only code blocks
Surface = Literal["editor", "static", "ide"]
Profile = Literal["professional", "student"]
Confidence = Literal["high", "medium", "speculative"]

TOPICS = [
    "arrays", "strings", "hashing", "two-pointers", "sliding-window", "stack-queue",
    "linked-list", "binary-search", "sorting", "recursion", "backtracking", "trees",
    "graphs", "heaps", "dynamic-programming", "greedy", "math", "bit-manipulation",
    "debugging", "environment-setup", "http-apis", "cors", "async", "databases",
    "git", "other",
]


class _Serializable:
    def to_dict(self) -> dict:
        return asdict(self)  # type: ignore[arg-type]

    @classmethod
    def from_dict(cls, d: dict):
        names = {f.name for f in fields(cls)}  # type: ignore[arg-type]
        return cls(**{k: v for k, v in d.items() if k in names})


@dataclass
class ContextLabel(_Serializable):
    mode: Mode
    platform: str                  # "leetcode", "hackerrank", "vscode", "localhost", ...
    problem_key: Optional[str]     # "leetcode:coin-change" | "project:todo-api" | None
    problem_title: Optional[str]   # "Coin Change"


@dataclass
class StuckSignal(_Serializable):
    id: str                        # "sig-<uuid8>"
    created_at: str                # ISO local time
    problem_key: str
    problem_title: Optional[str]
    mode: Mode
    platform: str
    minutes_on_problem: float      # measured: problem + attributed help time
    loops: int                     # measured: problem -> help -> problem cycles
    keys_per_min: float            # measured: keystrokes / problem minutes
    rules_fired: list[str]         # ["R1_time", "R2_loop", "R3_low_input"]
    frame_ids: list[str]           # ["f-0007", "f-0009", ...]
    needs_judgement: bool          # True -> send to Gemma judge
    status: Literal["pending", "confirmed", "rejected", "offered",
                    "accepted", "dismissed", "snoozed"] = "pending"
    judge_reason: Optional[str] = None


@dataclass
class HintRequest(_Serializable):
    signal_id: str
    problem_key: str
    problem_title: Optional[str]
    mode: Mode
    level: int                     # 1 nudge, 2 concept, 3 plan, 4 full code (project only)
    user_context: Optional[str] = None
    previous_hints: list[str] = field(default_factory=list)


@dataclass
class HintResponse(_Serializable):
    signal_id: str
    level: int
    text: str
    is_code: bool                  # True only for project-mode code
    blocked: bool = False
    block_reason: Optional[str] = None


@dataclass
class SessionRecord(_Serializable):
    problem_key: str
    problem_title: Optional[str]
    platform: str
    mode: Mode
    topics: list[str]
    first_seen: str
    last_seen: str
    active_min: float
    stuck_episodes: int
    hints_used: int
    max_hint_level: int
    time_to_unstuck_min: Optional[float]
    solved: Optional[bool]
    frame_ids: list[str]


@dataclass
class CodeSuggestion(_Serializable):
    id: str                        # "sug-<uuid6>"
    start_line: int                # 1-based, computed by US from `quote`, never trusted from Gemma
    end_line: int
    quote: str                     # exact text from the user's code
    issue: str                     # "Nested loop over the same array"
    why: str
    complexity_before: Optional[str]   # "O(n²)"
    complexity_after: Optional[str]    # "O(n)"
    suggestion: str                # plain-English better approach (always present)
    replacement: Optional[str]     # faster code — None when policy forbids code
    confidence: Confidence


@dataclass
class ReportClaim(_Serializable):
    id: str
    kind: Literal["strength", "weakness", "trend", "recommendation"]
    text: str
    topic: Optional[str]
    numeric_claims: dict
    about_problems: list[str]
    confidence: Confidence
    gate_status: Literal["unchecked", "passed", "downgraded", "rejected"] = "unchecked"
    gate_reason: Optional[str] = None
    recomputed: dict = field(default_factory=dict)
