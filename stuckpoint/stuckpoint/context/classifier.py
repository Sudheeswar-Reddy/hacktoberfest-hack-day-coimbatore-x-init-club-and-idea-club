"""Context classifier (Person 1): Activity Frames frame -> ContextLabel.

Stateless and deterministic. The help policy itself lives in sites.py.
Note: frames carry the site and window titles, not the full URL, so problem
names come from the window title (e.g. "322. Coin Change - LeetCode").
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from ..models import ContextLabel
from .sites import (
    EXAM,
    HELP_PAGE_KINDS,
    HELP_SITES,
    ONLINE_EDITORS,
    PRACTICE,
    PROJECT_APPS,
    PROJECT_PAGE_KINDS,
    TERMINAL_APPS,
    TITLE_NOISE,
)

_GENERIC_TITLES = {"", "leetcode", "problems", "problem list", "submissions",
                   "description", "editorial", "solutions", "hackerrank", "codeforces"}


def _site_lookup(site: str | None, table: dict[str, str]) -> str | None:
    """Match a site against a table, also matching parent domains."""
    if not site:
        return None
    parts = site.split(".")
    for i in range(len(parts) - 1):
        hit = table.get(".".join(parts[i:]))
        if hit:
            return hit
    return None


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def clean_title(window: str) -> str:
    """'322. Coin Change - LeetCode - Google Chrome' -> 'Coin Change'."""
    t = window.replace("​", "").strip()   # Edge puts a zero-width space in "Microsoft​ Edge"
    t = re.sub(r" and \d+ more pages?(?= - )", "", t)   # Edge tab-group suffix
    changed = True
    while changed:                         # strip stacked suffixes
        changed = False
        for noise in TITLE_NOISE:
            if t.endswith(noise):
                t = t[: -len(noise)].rstrip()
                changed = True
    t = re.sub(r"^\(\d+\)\s*", "", t)          # "(3) Title" notification counters
    t = re.sub(r"^\d+\.\s*", "", t)            # "322. Coin Change"
    t = re.sub(r"\s+-\s+(Submissions|Description|Editorial|Solutions)$", "", t, flags=re.I)
    t = re.sub(r"^(Problem\s*-\s*\w+\s*-\s*)", "", t)  # Codeforces "Problem - 1A - Title"
    return t.strip()


def _problem_title(frame: dict) -> str | None:
    for w in frame.get("windows") or []:
        t = clean_title(w)
        if t.lower() not in _GENERIC_TITLES:
            return t
    return None


def _project_name(frame: dict) -> str | None:
    """Editor title -> workspace name.

    'app.py — todo-api — Visual Studio Code' (Windows/Linux) -> 'todo-api'
    'app.py — todo-api'                       (macOS)         -> 'todo-api'
    """
    for w in frame.get("windows") or []:
        parts = [p.strip() for p in re.split(r"\s[—–-]\s", w) if p.strip()]
        if parts and parts[-1] in PROJECT_APPS:
            parts = parts[:-1]
        if parts:
            return parts[-1]
    return None


def _online_name(frame: dict) -> str | None:
    """'todo-app - CodeSandbox - Google Chrome' -> 'todo-app'."""
    for w in frame.get("windows") or []:
        t = clean_title(w)
        first = re.split(r"\s[—–|·-]\s", t)[0].strip()
        if first:
            return first
    return None


def page_kinds(frame: dict) -> set[str]:
    return {p.get("kind", "") for p in frame.get("pages") or []}


def is_help(frame: dict) -> bool:
    """True if the frame is the user looking for help (search, Q&A, AI chat)."""
    if page_kinds(frame) & HELP_PAGE_KINDS:
        return True
    # exact host match on purpose: docs.google.com is not "help", google.com is
    return frame.get("site") in HELP_SITES


def host_of(url: str | None) -> str | None:
    """'https://www.leetcode.com/problems/x' -> 'leetcode.com' (same rule as Activity Frames)."""
    if not url:
        return None
    try:
        host = urlsplit(url if "//" in url else "//" + url).hostname
    except ValueError:
        return None
    if not host:
        return None
    return host[4:] if host.startswith("www.") else host


def mode_for(url: str | None, surface: str | None) -> str:
    """Suggestion mode from where the code is (instructions Part 3.3, step 1).

    exam site -> exam; practice site -> practice; ide, or an editor on any other
    site -> project; a read-only code block -> review; anything else -> other.
    """
    host = host_of(url)
    if _site_lookup(host, EXAM):
        return "exam"
    if _site_lookup(host, PRACTICE):
        return "practice"
    if surface in ("ide", "editor"):
        return "project"
    if surface == "static":
        return "review"
    return "other"


def classify(frame: dict) -> ContextLabel:
    site = frame.get("site")
    app = frame.get("app", "")

    exam = _site_lookup(site, EXAM)
    if exam:
        return ContextLabel(mode="exam", platform=exam, problem_key=None, problem_title=None)

    practice = _site_lookup(site, PRACTICE)
    if practice:
        title = _problem_title(frame)
        key = f"{practice}:{slugify(title)}" if title else None
        return ContextLabel(mode="practice", platform=practice, problem_key=key, problem_title=title)

    online = _site_lookup(site, ONLINE_EDITORS)
    if online:
        # vscode.dev / github.dev titles look like VS Code's; the others are "<project> - <Site>"
        name = _project_name(frame) if online in ("vscode.dev", "github.dev") else _online_name(frame)
        key = f"project:{slugify(name)}" if name else None
        return ContextLabel(mode="project", platform=online, problem_key=key, problem_title=name)

    if app in PROJECT_APPS:
        name = _project_name(frame)
        key = f"project:{slugify(name)}" if name else None
        return ContextLabel(mode="project", platform=PROJECT_APPS[app], problem_key=key, problem_title=name)

    # Project-related but unnamed (localhost, terminal, GitHub): the detector
    # attributes these to whichever project the user is currently on.
    if app in TERMINAL_APPS:
        return ContextLabel(mode="project", platform="terminal", problem_key=None, problem_title=None)
    if page_kinds(frame) & PROJECT_PAGE_KINDS:
        platform = "localhost" if "local_dev" in page_kinds(frame) else (site or "web")
        return ContextLabel(mode="project", platform=platform, problem_key=None, problem_title=None)

    return ContextLabel(mode="other", platform=site or app or "unknown", problem_key=None, problem_title=None)
