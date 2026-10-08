"""StuckPoint local engine (Person 1): the HTTP API the Chrome and VS Code extensions use.

    python -m stuckpoint serve        -> http://127.0.0.1:8765

Routes follow instructions.md Part 3.2. The extensions are the recorder on every
OS: they POST activity to /events, which ingest.py writes in Activity Frames'
capture schema. A background thread runs the detector (watcher.run_once) every
CHECK_INTERVAL_S; the extensions poll /status for stuck signals.
"""
from __future__ import annotations

import threading
import time
import traceback
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import config
from .capture.source import get_frames, now
from .context.classifier import classify
from .ingest import ingest
from .llm.hints import MAX_LEVEL, next_hint, project_help
from .llm.suggest import code_allowed, suggest_with_stats
from .models import HintRequest
from .store.db import Store

SIGNAL_TTL_MIN = 60          # don't show signals older than this
_store: Optional[Store] = None
_stop = threading.Event()
_loop_state = {"last_run": None, "last_error": None, "runs": 0}
_status_cache: dict = {"at": 0.0, "context": None}


def store() -> Store:
    global _store
    if _store is None or _store.path != config.STUCKPOINT_DB:
        _store = Store()
    return _store


def run_detection() -> list:
    """One detector pass (also used by POST /check and the background loop)."""
    from .watcher import run_once

    sigs = run_once(store(), notify=lambda *a: None, verbose=True)
    _loop_state.update(last_run=now().isoformat(timespec="seconds"), last_error=None)
    _loop_state["runs"] += 1
    return sigs


def _detection_loop() -> None:
    while not _stop.is_set():
        try:
            run_detection()
        except FileNotFoundError as e:      # no capture data yet
            _loop_state["last_error"] = str(e)
        except Exception as e:              # never let the loop die
            _loop_state["last_error"] = f"{type(e).__name__}: {e}"
            traceback.print_exc()
        _stop.wait(config.CHECK_INTERVAL_S)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _stop.clear()
    t = threading.Thread(target=_detection_loop, name="detector", daemon=True)
    t.start()
    print(f"[engine] source={config.SOURCE} capture={config.AFRAMES_DB} "
          f"threshold={config.STUCK_THRESHOLD_MIN} min model={config.GEMMA_MODEL}")
    yield
    _stop.set()


app = FastAPI(title="StuckPoint engine", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---- request bodies ----------------------------------------------------------
Mode = Literal["practice", "project", "review", "exam", "other"]


class EventsIn(BaseModel):
    source: Literal["chrome", "vscode", "recorder"] = "chrome"
    events: list[dict] = Field(default_factory=list, max_length=2000)


class StatusIn(BaseModel):
    status: Literal["offered", "accepted", "dismissed", "snoozed"]


class HintIn(BaseModel):
    signal_id: str = ""
    problem_key: str
    problem_title: Optional[str] = None
    mode: Mode
    level: Optional[int] = None          # omitted -> next level after the stored hints
    user_context: Optional[str] = Field(default=None, max_length=8000)
    previous_hints: list[str] = Field(default_factory=list)


class SuggestIn(BaseModel):
    code: str = Field(max_length=200_000)
    language: str = ""
    url: Optional[str] = None            # page the code is on (null for IDEs)
    surface: Literal["editor", "static", "ide"] = "editor"
    profile: Literal["professional", "student"] = "professional"
    solved: bool = False
    problem_title: Optional[str] = None


class SolvedIn(BaseModel):
    problem_key: str
    solved: bool = True


# ---- routes ------------------------------------------------------------------
@app.get("/health")
def health():
    return {"ok": True, "model": config.GEMMA_MODEL, "source": config.SOURCE,
            "llm_configured": bool(config.GEMINI_API_KEY), "detector": _loop_state}


@app.post("/events")
def post_events(body: EventsIn):
    return {"ok": True, "stored": ingest(body.events, body.source)}


def _current_context() -> Optional[dict]:
    if time.time() - _status_cache["at"] < 3:
        return _status_cache["context"]
    try:
        frames = get_frames(10)
    except FileNotFoundError:
        frames = []
    ctx = classify(frames[-1]).to_dict() if frames else None
    _status_cache.update(at=time.time(), context=ctx)
    return ctx


@app.get("/status")
def status():
    sig = store().latest_signal()
    if sig is not None:
        try:
            from datetime import datetime

            if now() - datetime.fromisoformat(sig.created_at) > timedelta(minutes=SIGNAL_TTL_MIN):
                sig = None
        except ValueError:
            pass
    return {"context": _current_context(), "signal": sig.to_dict() if sig else None}


@app.post("/check")
def check_now():
    """'Check now' button: run one detection pass immediately."""
    try:
        sigs = run_detection()
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e), "signals": []}
    return {"ok": True, "signals": [s.to_dict() for s in sigs]}


@app.post("/signal/{signal_id}/status")
def signal_status(signal_id: str, body: StatusIn):
    if not store().update_signal_status(signal_id, body.status):
        raise HTTPException(404, f"unknown signal {signal_id}")
    return {"ok": True}


def _hint_request(body: HintIn) -> HintRequest:
    stored = store().hints_for(body.problem_key, body.signal_id or None)
    previous = body.previous_hints or [h.text for h in stored]
    level = body.level if body.level is not None else min(len(stored) + 1, MAX_LEVEL)
    return HintRequest(signal_id=body.signal_id, problem_key=body.problem_key,
                       problem_title=body.problem_title, mode=body.mode, level=level,
                       user_context=body.user_context, previous_hints=previous)


def _record_hint(req: HintRequest, resp) -> None:
    if req.mode not in ("practice", "project"):
        return
    s = store()
    s.save_hint(resp, req.problem_key)
    sig = s.get_signal(req.signal_id) if req.signal_id else None
    if sig and sig.status in ("confirmed", "offered"):
        s.update_signal_status(sig.id, "accepted")


@app.post("/hint")
def hint(body: HintIn):
    req = _hint_request(body)
    resp = next_hint(req)
    _record_hint(req, resp)
    return resp.to_dict()


@app.post("/help/full")
def help_full(body: HintIn):
    req = _hint_request(body)
    req.level = 4 if body.level is None else body.level
    try:
        resp = project_help(req)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    _record_hint(req, resp)
    return resp.to_dict()


@app.post("/suggest")
def post_suggest(body: SuggestIn):
    """The engine decides the mode from url + surface (Part 3.3); the UI just renders."""
    mode, sugs, dropped = suggest_with_stats(body.code, body.language, body.url, body.surface,
                                             body.profile, body.solved, body.problem_title)
    return {"mode": mode, "suggestions": [s.to_dict() for s in sugs], "dropped": dropped,
            "code_allowed": code_allowed(mode, body.profile, body.solved)}


@app.post("/solved")
def solved(body: SolvedIn):
    store().mark_solved(body.problem_key, body.solved)
    return {"ok": True}


@app.get("/report")
def report():
    from .report.build import build_report

    return build_report(store())


@app.get("/frames")
def frames(minutes: int = 60):
    """Debug: what Activity Frames compiled from the capture, with our classification."""
    try:
        fs = get_frames(minutes)
    except FileNotFoundError as e:
        return {"frames": [], "error": str(e)}
    return {"frames": [{**f, "context": classify(f).to_dict()} for f in fs]}


def serve() -> None:
    import uvicorn

    uvicorn.run(app, host=config.ENGINE_HOST, port=config.ENGINE_PORT, log_level="info")
