"""Linux capture backend (X11). Needs `xdotool`; `xprintidle` is optional.

Browsers expose no URL API on Linux, so URLs come from window titles
(url_source='title'). Wayland sessions block window inspection by design:
run an X11 session or use fixture mode.
"""
from __future__ import annotations

import shutil
import subprocess
from typing import Optional

from ..recorder import Focus
from .common import BROWSERS, PynputInput, app_name, url_from_title


def _run(*args: str) -> str:
    return subprocess.run(list(args), capture_output=True, text=True, timeout=2).stdout.strip()


class LinuxBackend(PynputInput):
    def __init__(self):
        super().__init__()
        if not shutil.which("xdotool"):
            print("[recorder] xdotool not found: sudo apt install xdotool")

    def foreground(self) -> Optional[Focus]:
        try:
            wid = _run("xdotool", "getactivewindow")
            if not wid:
                return None
            title = _run("xdotool", "getwindowname", wid)
            pid = _run("xdotool", "getwindowpid", wid)
            with open(f"/proc/{pid}/comm", encoding="utf-8") as f:
                proc = f.read().strip()
        except Exception:
            return None
        app = app_name(proc)
        url = url_from_title(title) if app in BROWSERS else None
        return Focus(app=app, title=title, url=url, url_source="title" if url else None)

    def idle_seconds(self) -> float:
        if not shutil.which("xprintidle"):
            return 0.0
        try:
            return int(_run("xprintidle")) / 1000.0
        except ValueError:
            return 0.0
