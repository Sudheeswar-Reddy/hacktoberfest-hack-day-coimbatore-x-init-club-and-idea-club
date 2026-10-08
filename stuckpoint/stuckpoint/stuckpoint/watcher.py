"""Watcher loop (Person 1): frames -> stuck signals -> Gemma judge -> store -> notify.

Runs as its own process: `python -m stuckpoint watch`.
Talks to the UI only through the store (Person 3) and OS notifications (Person 4).
Until those modules exist, it falls back to an in-memory store and console output.
"""
from __future__ import annotations

import time
import traceback

from . import config
from .capture.source import get_frames, now
from .detector.stuck import detect
from .llm.judge import judge_stuck
from .models import StuckSignal


class _MemoryStore:
    """Stand-in until Person 3's Store lands. Same method names."""

    def __init__(self):
        self.signals: list[StuckSignal] = []
        self.frames: dict[str, dict] = {}

    def save_signal(self, sig: StuckSignal) -> None:
        self.signals.append(sig)

    def last_signal_for(self, problem_key: str):
        for sig in reversed(self.signals):
            if sig.problem_key == problem_key:
                return sig
        return None

    def save_frames(self, frames: list[dict]) -> None:
        for f in frames:
            self.frames[f["id"]] = f


def _get_store():
    try:
        from .store.db import Store  # Person 3

        return Store()
    except Exception:
        print("[watcher] store/db.py not ready — using in-memory store")
        return _MemoryStore()


def _get_notify():
    try:
        from .ui.notify import notify  # Person 4

        return notify
    except Exception:
        return lambda title, body: print(f"[notify] {title}: {body}")


def run_once(store, notify, *, verbose: bool = True) -> list[StuckSignal]:
    frames = get_frames(60)
    current_time = now()
    signals = detect(frames, current_time, store=store)
    for sig in signals:
        if sig.needs_judgement:
            stuck, reason = judge_stuck(sig, frames)
            sig.status = "confirmed" if stuck else "rejected"
            sig.judge_reason = reason
        else:
            sig.status = "confirmed"
            sig.judge_reason = "rules: " + ", ".join(sig.rules_fired)
        store.save_signal(sig)
        if verbose:
            print(f"[watcher] {sig.status.upper()} {sig.problem_key} "
                  f"({sig.minutes_on_problem} min, {sig.loops} loops, {sig.keys_per_min} keys/min) "
                  f"— {sig.judge_reason}")
        if sig.status == "confirmed":
            title = sig.problem_title or sig.problem_key
            notify("StuckPoint", f"Stuck on {title}? Open StuckPoint for a hint.")
    store.save_frames(frames)
    return signals


def watch(once: bool = False) -> None:
    store, notify = _get_store(), _get_notify()
    print(f"[watcher] source={config.SOURCE} threshold={config.STUCK_THRESHOLD_MIN} min "
          f"interval={config.CHECK_INTERVAL_S}s model={config.GEMMA_MODEL}")
    while True:
        try:
            run_once(store, notify)
        except KeyboardInterrupt:
            raise
        except FileNotFoundError as e:  # RecorderDBNotFound: capture not started yet
            print(f"[watcher] {e}")
        except Exception:  # never let one bad cycle kill the watcher
            traceback.print_exc()
        if once:
            return
        time.sleep(config.CHECK_INTERVAL_S)
