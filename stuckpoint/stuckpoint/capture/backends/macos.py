"""macOS capture backend (fallback when the official `aframes record` engine isn't used).

Prefer Activity Frames' own engine on macOS (`aframes record`). This backend
exists so `python -m stuckpoint record` works the same on every OS.
Needs Accessibility permission for the terminal running it (window titles,
input counting) and Automation permission for browsers (URLs).
"""
from __future__ import annotations

import re
import subprocess
from typing import Optional

from ..recorder import Focus
from .common import BROWSERS, PynputInput, app_name, normalize_url, url_from_title

_FRONT = '''
tell application "System Events"
    set p to first application process whose frontmost is true
    set n to name of p
    set t to ""
    try
        set t to name of front window of p
    end try
end tell
return n & "\n" & t
'''

_URL = {
    "Safari": 'tell application "Safari" to return URL of front document',
    "Firefox": None,   # no AppleScript URL API; title fallback
}
_CHROMIUM = 'tell application "{app}" to return URL of active tab of front window'


def _osa(script: str) -> str:
    out = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=3)
    return out.stdout.strip()


class MacBackend(PynputInput):
    def __init__(self):
        super().__init__()
        self._url_cache: dict[tuple[str, str], Optional[str]] = {}

    def foreground(self) -> Optional[Focus]:
        try:
            name, _, title = _osa(_FRONT).partition("\n")
        except Exception:
            return None
        if not name:
            return None
        app = app_name(name)
        url, source = None, None
        if app in BROWSERS:
            key = (app, title)
            if key not in self._url_cache:
                script = _URL.get(app, _CHROMIUM.format(app=app))
                try:
                    self._url_cache[key] = normalize_url(_osa(script)) if script else None
                except Exception:
                    self._url_cache[key] = None
            url = self._url_cache[key]
            source = "browser" if url else None
            if not url:
                url = url_from_title(title)
                source = "title" if url else None
        return Focus(app=app, title=title, url=url, url_source=source)

    def idle_seconds(self) -> float:
        try:
            out = subprocess.run(["ioreg", "-c", "IOHIDSystem"], capture_output=True, text=True,
                                 timeout=3).stdout
            m = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', out)
            return int(m.group(1)) / 1e9 if m else 0.0
        except Exception:
            return 0.0
