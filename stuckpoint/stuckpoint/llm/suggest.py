"""Inline code suggestions (Person 2): find slow/clumsy lines, verified by quote.

suggest(code, language, url, surface, profile, solved, problem_title=None)
    -> (mode, list[CodeSuggestion])
suggest_with_stats(...) -> (mode, suggestions, dropped)   # dropped = hallucinated quotes

The same idea as the evidence gate, applied to code: Gemma must copy the exact
lines it means into `quote`. WE locate the quote in the user's code and compute
start_line/end_line; a quote that can't be found is dropped. Model line numbers
are never used.

Step 1 - the ENGINE decides the mode from url + surface (context.classifier.mode_for):
  exam site -> exam; practice site -> practice; ide / editor elsewhere -> project;
  read-only code block (static) -> review.

Step 2 - policy (instructions Part 3.3). The explanation is always returned; code only when:
  practice   solved
  project    profile == "professional", or solved ("Show me" resends with solved=true)
  review     always
  exam/other -> no suggestions at all
When code is withheld, replacement=None and issue/why/suggestion pass the no-code guard.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Optional

from .. import config
from ..models import CodeSuggestion
from .client import LLMError, _log, gemma_json
from .guard import check_no_code
from .prompting import render

MAX_SUGGESTIONS = 3

SCHEMA = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "object",
                "properties": {
                    "quote": {"type": "string", "minLength": 1},
                    "issue": {"type": "string", "minLength": 1},
                    "why": {"type": "string"},
                    "complexity_before": {"type": ["string", "null"]},
                    "complexity_after": {"type": ["string", "null"]},
                    "suggestion": {"type": "string", "minLength": 1},
                    "replacement": {"type": ["string", "null"]},
                    "confidence": {"type": "string", "enum": ["high", "medium", "speculative"]},
                },
                "required": ["quote", "issue", "why", "suggestion", "confidence"],
            },
        }
    },
    "required": ["suggestions"],
}

SAFE_ISSUE = "This part does more work than it needs to"
SAFE_WHY = "Something here is repeated or recomputed more often than necessary."
SAFE_SUGGESTION = ("Ask yourself what work is repeated here, and whether a different data "
                   "structure would let you find what you need without scanning again.")

_cache: dict[str, tuple[list[CodeSuggestion], int]] = {}

PROFILES = ("professional", "student")


def _norm(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip())


def locate(code: str, quote: str) -> Optional[tuple[int, int]]:
    """1-based (start_line, end_line) of `quote` in `code`, whitespace-insensitive per
    line and ignoring blank lines. Falls back to matching the quote's first 2 lines."""
    q = [_norm(l) for l in quote.strip("\n").splitlines() if l.strip()]
    if not q:
        return None
    lines = [(i + 1, _norm(l)) for i, l in enumerate(code.splitlines()) if l.strip()]
    texts = [t for _, t in lines]

    def find(seq: list[str]) -> Optional[int]:
        for i in range(len(texts) - len(seq) + 1):
            if texts[i:i + len(seq)] == seq:
                return i
        return None

    i = find(q)
    if i is not None:
        return lines[i][0], lines[i + len(q) - 1][0]
    if len(q) > 2:
        i = find(q[:2])
        if i is not None:
            j = min(i + len(q) - 1, len(lines) - 1)
            return lines[i][0], lines[j][0]
    return None


def _numbered(code: str) -> str:
    return "\n".join(f"{i:>4} | {l}" for i, l in enumerate(code.splitlines(), 1))


def _clean(s: Optional[str]) -> Optional[str]:
    s = (s or "").strip()
    return s or None


def schema_for(allow_code: bool) -> dict:
    """When code is allowed, `replacement` is required (the model otherwise picks null);
    a reply without it fails validation and gemma_json retries with the error."""
    if not allow_code:
        return SCHEMA
    import copy

    s = copy.deepcopy(SCHEMA)
    item = s["properties"]["suggestions"]["items"]
    item["properties"]["replacement"] = {"type": "string", "minLength": 1}
    item["required"] = item["required"] + ["replacement"]
    return s


def code_allowed(mode: str, profile: str, solved: bool) -> bool:
    """Part 3.3 table: may `replacement` (code) be returned?"""
    if mode == "review":
        return True
    if mode == "practice":
        return bool(solved)
    if mode == "project":
        return profile != "student" or bool(solved)
    return False


def suggest(code: str, language: str = "", url: Optional[str] = None, surface: str = "editor",
            profile: str = "professional", solved: bool = False,
            problem_title: Optional[str] = None) -> tuple[str, list[CodeSuggestion]]:
    mode, sugs, _ = suggest_with_stats(code, language, url, surface, profile, solved, problem_title)
    return mode, sugs


def suggest_with_stats(code: str, language: str = "", url: Optional[str] = None,
                       surface: str = "editor", profile: str = "professional", solved: bool = False,
                       problem_title: Optional[str] = None, *, mode: Optional[str] = None,
                       ) -> tuple[str, list[CodeSuggestion], int]:
    """Returns (mode, verified suggestions, number dropped because their quote wasn't found).
    `mode` can be forced (CLI / language server); normally it is derived from url + surface."""
    from ..context.classifier import mode_for

    mode = mode or mode_for(url, surface)
    profile = profile if profile in PROFILES else "professional"
    if mode not in ("practice", "project", "review") or not code or not code.strip():
        return mode, [], 0
    code = "\n".join(code.splitlines()[:config.SUGGEST_MAX_LINES])
    allow_code = code_allowed(mode, profile, solved)
    key = hashlib.sha256(json.dumps(
        [code, language, problem_title, mode, profile, bool(solved)]).encode()).hexdigest()
    if key in _cache:
        return (mode, *_cache[key])

    prompt = render(
        "suggest",
        language=language.strip() or "(unknown - infer it from the code)",
        problem_title=problem_title or "(unknown)",
        numbered_code=_numbered(code),
        replacement_rule=(
            "REQUIRED - the complete improved code that replaces exactly the quoted lines, with the "
            "same indentation, so it can be pasted over them. Never null."
            if allow_code else
            "always null. Do NOT write any code anywhere in your answer; describe the idea in "
            "plain English only."),
    )
    try:
        out = gemma_json(prompt, schema_for(allow_code), system=render("system_tutor"),
                         temperature=0.2, use_cache=False)
    except LLMError:
        return mode, [], 0                # not cached: try again next time

    result: list[CodeSuggestion] = []
    seen: set[tuple[int, int]] = set()
    dropped = 0
    for s in out["suggestions"]:
        where = locate(code, s["quote"])
        if where is None or where in seen:
            dropped += where is None
            continue
        seen.add(where)
        issue, why, text = s["issue"].strip(), (s.get("why") or "").strip(), s["suggestion"].strip()
        replacement = _clean(s.get("replacement")) if allow_code else None
        if not allow_code:                # code withheld: none anywhere in the card
            issue = issue if check_no_code(issue)[0] else SAFE_ISSUE
            why = why if check_no_code(why)[0] else SAFE_WHY
            text = text if check_no_code(text)[0] else SAFE_SUGGESTION
        result.append(CodeSuggestion(
            id=f"sug-{uuid.uuid4().hex[:6]}",
            start_line=where[0], end_line=where[1],
            quote="\n".join(code.splitlines()[where[0] - 1:where[1]]),   # the user's real lines
            issue=issue, why=why,
            complexity_before=_clean(s.get("complexity_before")),
            complexity_after=_clean(s.get("complexity_after")),
            suggestion=text, replacement=replacement,
            confidence=s["confidence"],
        ))
        if len(result) == MAX_SUGGESTIONS:
            break
    _log({"suggest": True, "mode": mode, "profile": profile, "solved": solved,
          "kept": len(result), "dropped": dropped})
    _cache[key] = (result, dropped)
    return mode, result, dropped


def card_markdown(s: CodeSuggestion, language: str = "") -> str:
    """The hover-card text (used by the language server; the extensions build their own)."""
    head = "**⚡ Faster approach**"
    if s.complexity_before and s.complexity_after:
        head += f" · {s.complexity_before} → {s.complexity_after}"
    parts = [head, s.issue + (f". {s.why}" if s.why else ""), f"*Try:* {s.suggestion}"]
    if s.replacement:
        parts.append(f"```{language}\n{s.replacement}\n```")
    return "\n\n".join(parts)
