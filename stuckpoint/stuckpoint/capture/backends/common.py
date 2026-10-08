"""Shared helpers for the capture backends: app names, URLs, input hooks."""
from __future__ import annotations

import re
from typing import Callable, Optional
from urllib.parse import quote

# Executable / process name (lower-case, no extension) -> the app name nocta
# reports on macOS, so the classifier tables in context/sites.py work everywhere.
APP_NAMES = {
    "chrome": "Google Chrome", "google-chrome": "Google Chrome", "chromium": "Chromium",
    "msedge": "Microsoft Edge", "microsoft-edge": "Microsoft Edge",
    "firefox": "Firefox", "brave": "Brave Browser", "opera": "Opera", "vivaldi": "Vivaldi",
    "arc": "Arc",
    "code": "Code", "code-insiders": "Code", "cursor": "Cursor", "windsurf": "Windsurf",
    "pycharm64": "PyCharm", "pycharm": "PyCharm", "idea64": "IntelliJ IDEA", "idea": "IntelliJ IDEA",
    "webstorm64": "WebStorm", "clion64": "CLion", "studio64": "Android Studio",
    "devenv": "Visual Studio", "sublime_text": "Sublime Text", "notepad++": "Notepad++",
    "zed": "Zed",
    "windowsterminal": "Windows Terminal", "powershell": "Windows PowerShell", "pwsh": "PowerShell",
    "cmd": "Command Prompt", "gnome-terminal-server": "Terminal", "konsole": "Konsole",
    "alacritty": "Alacritty", "kitty": "kitty", "wezterm-gui": "WezTerm",
    "slack": "Slack", "discord": "Discord", "teams": "Microsoft Teams", "ms-teams": "Microsoft Teams",
    "explorer": "File Explorer", "spotify": "Spotify",
}

BROWSERS = {"Google Chrome", "Chromium", "Microsoft Edge", "Firefox", "Brave Browser",
            "Opera", "Vivaldi", "Arc", "Safari"}


def app_name(process_name: str) -> str:
    stem = re.sub(r"\.(exe|app)$", "", process_name.strip(), flags=re.I)
    return APP_NAMES.get(stem.lower(), stem)


def normalize_url(raw: Optional[str]) -> Optional[str]:
    """Address-bar text -> URL. Chromium hides the scheme; the user may be mid-typing."""
    if not raw:
        return None
    v = raw.strip()
    if not v or " " in v:
        return None                       # typing a search, not a URL
    if re.match(r"^[a-z][a-z0-9+.-]*://", v, re.I):
        return v
    if re.match(r"^(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])(:\d+)?(/|$)", v):
        return "http://" + v
    if re.match(r"^[\w-]+(\.[\w-]+)+(:\d+)?(/|$)", v):
        return "https://" + v
    return None


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# Fallback when the browser URL can't be read (no accessibility API, Wayland,
# omnibox focused...). Derived only from the window title, which IS measured;
# rows written this way are tagged url_source='title' in the frames table.
_TITLE_RULES: list[tuple[re.Pattern, Callable[[re.Match], str]]] = [
    (re.compile(r"^(?:\(\d+\)\s*)?(?:\d+\.\s*)?(?P<t>.+?)\s[-|]\s(?:Submissions\s-\s)?LeetCode\b"),
     lambda m: "https://leetcode.com/problems/" + _slug(m["t"]) + "/"),
    (re.compile(r"\bLeetCode\b"), lambda m: "https://leetcode.com/"),
    (re.compile(r"\bHackerRank\b"), lambda m: "https://www.hackerrank.com/"),
    (re.compile(r"\bCodeforces\b"), lambda m: "https://codeforces.com/"),
    (re.compile(r"\bCodeChef\b"), lambda m: "https://www.codechef.com/"),
    (re.compile(r"\bGeeksforGeeks\b"), lambda m: "https://www.geeksforgeeks.org/"),
    (re.compile(r"^(?P<q>.+?) - Google Search\b"),
     lambda m: "https://www.google.com/search?q=" + quote(m["q"])),
    (re.compile(r"^(?P<q>.+?) - Bing\b"), lambda m: "https://www.bing.com/search?q=" + quote(m["q"])),
    (re.compile(r"\bStack Overflow\b"), lambda m: "https://stackoverflow.com/"),
    (re.compile(r"^ChatGPT\b|\bChatGPT$"), lambda m: "https://chatgpt.com/"),
    (re.compile(r"\bClaude\b"), lambda m: "https://claude.ai/"),
    (re.compile(r"^Gemini\b"), lambda m: "https://gemini.google.com/"),
    (re.compile(r"\bGitHub\b"), lambda m: "https://github.com/"),
]


def url_from_title(title: str) -> Optional[str]:
    for pattern, build in _TITLE_RULES:
        m = pattern.search(title or "")
        if m:
            return build(m)
    return None


class PynputInput:
    """Key/click counting via pynput (macOS, Linux/X11). Only the fact of a press is kept."""

    def __init__(self):
        self._listeners = []

    def start_input(self, cb) -> None:
        try:
            from pynput import keyboard, mouse
        except Exception as e:  # not installed, or no display server access
            print(f"[recorder] input counting disabled ({e}); pip install pynput")
            return
        k = keyboard.Listener(on_press=lambda key: cb("key"))
        m = mouse.Listener(on_click=lambda x, y, button, pressed:
                           cb("click", int(x), int(y)) if pressed else None)
        for listener in (k, m):
            listener.daemon = True
            listener.start()
            self._listeners.append(listener)

    def stop_input(self) -> None:
        for listener in self._listeners:
            listener.stop()
        self._listeners.clear()
