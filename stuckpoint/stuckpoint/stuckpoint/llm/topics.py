"""tag_topics (Person 2): problem title -> 1-3 topics from the shared vocabulary."""
from __future__ import annotations

from ..models import TOPICS
from .client import LLMError, gemma_json
from .prompting import render

SCHEMA = {
    "type": "object",
    "properties": {
        "topics": {
            "type": "array",
            "items": {"type": "string", "enum": TOPICS},
            "minItems": 1,
            "maxItems": 3,
        }
    },
    "required": ["topics"],
}

_cache: dict[tuple[str, str], list[str]] = {}


def tag_topics(title: str | None, platform: str) -> list[str]:
    """Never raises; returns ["other"] if Gemma is unavailable."""
    if not title:
        return ["other"]
    key = (title.strip().lower(), platform)
    if key in _cache:
        return _cache[key]
    try:
        out = gemma_json(
            render("tag_topics", title=title, platform=platform, vocabulary=", ".join(TOPICS)),
            SCHEMA, temperature=0.1,
        )
        topics = list(dict.fromkeys(out["topics"]))  # de-dupe, keep order
    except LLMError:
        return ["other"]                  # don't cache failures
    _cache[key] = topics
    return topics
