import pytest

from stuckpoint import config


@pytest.fixture(autouse=True)
def _defaults(monkeypatch, tmp_path):
    """Known thresholds for every test, regardless of the developer's .env."""
    monkeypatch.setattr(config, "STUCK_THRESHOLD_MIN", 15.0)
    monkeypatch.setattr(config, "LOOP_THRESHOLD", 3)
    monkeypatch.setattr(config, "LOW_INPUT_MIN", 10.0)
    monkeypatch.setattr(config, "LOW_INPUT_KPM", 8.0)
    monkeypatch.setattr(config, "WINDOW_MIN", 30.0)
    monkeypatch.setattr(config, "COOLDOWN_MIN", 10.0)
    monkeypatch.setattr(config, "SNOOZE_MIN", 15.0)
    monkeypatch.setattr(config, "LLM_LOG", str(tmp_path / "llm.jsonl"))
