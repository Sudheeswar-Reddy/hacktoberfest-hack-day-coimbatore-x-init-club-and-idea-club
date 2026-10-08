"""draft_report_claims (Person 2): metrics -> ReportClaims for P3's evidence gate.

Gemma only *drafts*. Every number is re-checked by report/gate.py before display.
"""
from __future__ import annotations

import json
import uuid

from ..models import ReportClaim
from .client import LLMError, gemma_json
from .prompting import render

CLAIM_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["strength", "weakness", "trend", "recommendation"]},
        "text": {"type": "string", "minLength": 1},
        "topic": {"type": ["string", "null"]},
        "numeric_claims": {"type": "object", "additionalProperties": {"type": "number"}},
        "about_problems": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["high", "medium", "speculative"]},
    },
    "required": ["kind", "text", "topic", "numeric_claims", "about_problems", "confidence"],
}

SCHEMA = {
    "type": "object",
    "properties": {"claims": {"type": "array", "items": CLAIM_SCHEMA, "minItems": 1, "maxItems": 10}},
    "required": ["claims"],
}


def draft_report_claims(metrics: dict) -> list[ReportClaim]:
    """Returns [] if Gemma is unavailable (the UI then shows metrics only)."""
    try:
        out = gemma_json(
            render("report_claims", metrics=json.dumps(metrics, indent=1)),
            SCHEMA, system=render("system_tutor"), temperature=0.3, use_cache=False,
        )
    except LLMError:
        return []
    claims = []
    for c in out["claims"]:
        claims.append(ReportClaim(
            id=f"clm-{uuid.uuid4().hex[:6]}",
            kind=c["kind"],
            text=c["text"].strip(),
            topic=c.get("topic"),
            numeric_claims=dict(c.get("numeric_claims") or {}),
            about_problems=list(c.get("about_problems") or []),
            confidence=c["confidence"],
        ))
    return claims
