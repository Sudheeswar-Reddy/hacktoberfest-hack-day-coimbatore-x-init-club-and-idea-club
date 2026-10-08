"""StuckPoint CLI.

  python -m stuckpoint record           capture activity on Windows / Linux / macOS (Ctrl+C stops)
  python -m stuckpoint record --background | --status | --stop
  python -m stuckpoint frames           show what Activity Frames compiled from the capture
  python -m stuckpoint watch            run the watcher loop (live capture or fixture)
  python -m stuckpoint watch --once     one detection pass, then exit
  python -m stuckpoint demo             detection on the fixture — no Mac / capture needed
  python -m stuckpoint hint             try a practice-mode hint on the demo problem (needs API key)
  python -m stuckpoint check-llm        smoke-test the Gemma 4 API connection
  python -m stuckpoint report           print the skills report (needs Person 3's report module)
"""
from __future__ import annotations

import argparse
import json
import sys


def _cmd_watch(args) -> int:
    from .watcher import watch

    try:
        watch(once=args.once)
    except KeyboardInterrupt:
        print("\n[watcher] stopped")
    return 0


def _cmd_demo(args) -> int:
    from . import config

    config.SOURCE = "fixture"
    from .capture.source import get_frames, now
    from .context.classifier import classify, is_help
    from .detector.stuck import detect

    frames = get_frames()
    print(f"Fixture: {config.FIXTURE}\n'now' = {now()}\n")
    print(f"{'frame':7} {'mode':9} {'problem':24} help  app / site")
    for f in frames:
        lab = classify(f)
        print(f"{f['id']:7} {lab.mode:9} {str(lab.problem_key):24} {'yes ' if is_help(f) else '    '}"
              f"  {f.get('app')} / {f.get('site', '-')}")
    sigs = detect(frames, now())
    print()
    if not sigs:
        print("No stuck signal.")
    for s in sigs:
        print(json.dumps(s.to_dict(), indent=2))
    return 0


def _cmd_hint(args) -> int:
    from .llm.hints import next_hint
    from .models import HintRequest

    previous: list[str] = []
    for level in (1, 2, 3):
        req = HintRequest(signal_id="sig-demo", problem_key="leetcode:coin-change",
                          problem_title="Coin Change", mode="practice", level=level,
                          user_context="just give me the code" if level == 3 else None,
                          previous_hints=previous)
        resp = next_hint(req)
        flag = f"  [BLOCKED: {resp.block_reason}]" if resp.blocked else ""
        print(f"\n--- Level {level}{flag}\n{resp.text}")
        previous.append(resp.text)
    return 0


def _cmd_check_llm(args) -> int:
    from . import config
    from .llm.client import LLMError, gemma_json

    try:
        out = gemma_json('Say hello. Return {"ok": true, "message": "<hello>"}.',
                         {"type": "object", "properties": {"ok": {"type": "boolean"},
                                                           "message": {"type": "string"}},
                          "required": ["ok", "message"]}, use_cache=False)
    except LLMError as e:
        print(f"FAILED ({config.GEMMA_MODEL}): {e}")
        return 1
    print(f"OK ({config.GEMMA_MODEL}): {out}")
    return 0


def _cmd_record(args) -> int:
    from .capture import recorder

    if args.status:
        print(recorder.status())
    elif args.stop:
        recorder.stop_recording()
    else:
        recorder.record(background=args.background)
    return 0


def _cmd_frames(args) -> int:
    """Compile recent capture with Activity Frames and show what the detector sees."""
    from .capture.source import capture_db, get_frames
    from .context.classifier import classify, is_help

    frames = get_frames(int(args.minutes))
    if args.json:
        print(json.dumps(frames, indent=2, ensure_ascii=False))
        return 0
    print(f"{len(frames)} frames from {capture_db()}\n")
    for f in frames:
        lab = classify(f)
        keys = (f.get("input") or {}).get("keys", 0)
        title = (f.get("windows") or [""])[0][:50]
        print(f"{f['start']}-{f['end']} {f['duration_min']:5}m {keys:5}k {lab.mode:8} "
              f"{'help ' if is_help(f) else '     '}{f.get('app')} / {f.get('site', '-')} | {title}")
    return 0


def _cmd_report(args) -> int:
    try:
        from .report.build import build_report  # Person 3
    except ImportError:
        print("report/build.py is not ready yet (Person 3).")
        return 1
    report = build_report()
    print(json.dumps(report, indent=2, default=lambda o: o.to_dict() if hasattr(o, "to_dict") else str(o)))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="stuckpoint", description="StuckPoint coding companion")
    sub = p.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("watch", help="run the watcher loop")
    w.add_argument("--once", action="store_true", help="single pass, then exit")
    w.set_defaults(func=_cmd_watch)
    sub.add_parser("demo", help="detection on the fixture").set_defaults(func=_cmd_demo)
    sub.add_parser("hint", help="try practice-mode hints (needs API key)").set_defaults(func=_cmd_hint)
    sub.add_parser("check-llm", help="smoke-test the Gemma API").set_defaults(func=_cmd_check_llm)
    sub.add_parser("report", help="print the skills report").set_defaults(func=_cmd_report)
    r = sub.add_parser("record", help="capture activity (Windows / Linux / macOS)")
    g = r.add_mutually_exclusive_group()
    g.add_argument("--background", action="store_true", help="run detached")
    g.add_argument("--stop", action="store_true", help="stop background capture")
    g.add_argument("--status", action="store_true", help="show capture status")
    r.set_defaults(func=_cmd_record)
    fr = sub.add_parser("frames", help="show compiled Activity Frames + classification")
    fr.add_argument("--minutes", type=float, default=60)
    fr.add_argument("--json", action="store_true")
    fr.set_defaults(func=_cmd_frames)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
