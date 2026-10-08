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
    # never touch real data: every test gets its own capture DB and store
    monkeypatch.setattr(config, "AFRAMES_DB", str(tmp_path / "capture.sqlite"))
    monkeypatch.setattr(config, "AFRAMES_DB_EXPLICIT", True)
    monkeypatch.setattr(config, "RECORDER_DB", str(tmp_path / "capture.sqlite"))
    monkeypatch.setattr(config, "STUCKPOINT_DB", str(tmp_path / "stuckpoint.db"))
    monkeypatch.setattr(config, "SOURCE", "live")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")   # no accidental real API calls
