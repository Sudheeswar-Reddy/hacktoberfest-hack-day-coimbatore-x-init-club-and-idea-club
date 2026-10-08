"""Load prompt templates from llm/prompts/*.md and fill $placeholders.

string.Template ($name) is used instead of str.format so JSON examples with
{braces} inside prompts don't need escaping.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from string import Template

_DIR = Path(__file__).resolve().parent / "prompts"


@lru_cache(maxsize=None)
def _load(name: str) -> Template:
    return Template((_DIR / f"{name}.md").read_text(encoding="utf-8"))


def render(name: str, **values) -> str:
    return _load(name).safe_substitute(**{k: str(v) for k, v in values.items()})
