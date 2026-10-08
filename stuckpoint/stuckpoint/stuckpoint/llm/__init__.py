"""Gemma 4 layer (Person 2). Public functions used by the rest of the team."""
from .client import LLMError, gemma_json
from .hints import next_hint, project_help
from .judge import judge_stuck
from .report_draft import draft_report_claims
from .topics import tag_topics

__all__ = ["LLMError", "gemma_json", "judge_stuck", "next_hint", "project_help",
           "tag_topics", "draft_report_claims"]
