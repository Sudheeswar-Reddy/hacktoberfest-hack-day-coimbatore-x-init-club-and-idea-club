"""Windows capture backend: Win32 via ctypes, browser URL via UI Automation.

- Foreground app/title: GetForegroundWindow + QueryFullProcessImageNameW.
- Browser URL: the address-bar Edit control, read with `uiautomation`
  (only re-read when the window title changes, so it's cheap).
- Input: WH_KEYBOARD_LL / WH_MOUSE_LL hooks on a dedicated thread. The key
  hook records only that a key went down - never which key.
"""
from __future__ import annotations

import ctypes
import os
import threading
from ctypes import wintypes
from typing import Optional

from ..recorder import Focus
from .common import BROWSERS, app_name, normalize_url, url_from_title

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

WH_KEYBOARD_LL, WH_MOUSE_LL = 13, 14
WM_KEYDOWN, WM_SYSKEYDOWN = 0x0100, 0x0104
WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN = 0x0201, 0x0204, 0x0207
WM_QUIT = 0x0012


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


def _process_name(pid: int) -> str:
    h = kernel32.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
        return ""
    finally:
        kernel32.CloseHandle(h)


class WindowsBackend:
    def __init__(self):
        self._url_cache: dict[tuple[int, str], Optional[str]] = {}
        self._uia = None            # lazily initialised on the polling thread
        self._uia_failed = False
        self._hook_thread: Optional[threading.Thread] = None
        self._hook_tid = 0

    # ---- focus ------------------------------------------------------------
    def foreground(self) -> Optional[Focus]:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None             # lock screen / secure desktop
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        title = buf.value
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        app = app_name(_process_name(pid.value) or "unknown")
        if app == "LockApp":
            return None
        url, source = None, None
        if app in BROWSERS:
            url = self._browser_url(hwnd, app, title)
            source = "browser" if url else None
            if not url:
                url = url_from_title(title)
                source = "title" if url else None
        return Focus(app=app, title=title, url=url, url_source=source)

    def _browser_url(self, hwnd, app: str, title: str) -> Optional[str]:
        key = (int(hwnd), title)
        if key in self._url_cache:
            return self._url_cache[key]
        url = None
        if not self._uia_failed:
            try:
                import uiautomation as auto

                if self._uia is None:
                    self._uia = auto.UIAutomationInitializerInThread(debug=False)
                    auto.SetGlobalSearchTimeout(1.0)
                win = auto.ControlFromHandle(hwnd)
                if app == "Firefox":
                    edit = win.EditControl(searchDepth=16, AutomationId="urlbar-input")
                else:   # Chromium: the omnibox is the first Edit in the toolbar
                    edit = win.EditControl(searchDepth=12)
                if edit.Exists(maxSearchSeconds=1.0, searchIntervalSeconds=0.2):
                    url = normalize_url(edit.GetValuePattern().Value)
            except ImportError:
                self._uia_failed = True
                print("[recorder] pip install uiautomation for exact browser URLs; using window titles")
            except Exception:
                url = None
        if len(self._url_cache) > 500:
            self._url_cache.clear()
        self._url_cache[key] = url
        return url

    def idle_seconds(self) -> float:
        info = LASTINPUTINFO(cbSize=ctypes.sizeof(LASTINPUTINFO))
        if not user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0
        return max(0, (kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000.0

    # ---- input hooks ------------------------------------------------------
    def start_input(self, cb) -> None:
        ready = threading.Event()

        def kb_proc(n_code, w_param, l_param):
            if n_code == 0 and w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                cb("key")
            return user32.CallNextHookEx(None, n_code, w_param, l_param)

        def mouse_proc(n_code, w_param, l_param):
            if n_code == 0 and w_param in (WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN):
                pt = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents.pt
                cb("click", pt.x, pt.y)
            return user32.CallNextHookEx(None, n_code, w_param, l_param)

        def loop():
            self._hook_tid = kernel32.GetCurrentThreadId()
            self._procs = (HOOKPROC(kb_proc), HOOKPROC(mouse_proc))   # keep refs alive
            hmod = kernel32.GetModuleHandleW(None)
            hooks = [user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._procs[0], hmod, 0),
                     user32.SetWindowsHookExW(WH_MOUSE_LL, self._procs[1], hmod, 0)]
            ready.set()
            if not all(hooks):
                print(f"[recorder] input hooks failed (error {ctypes.get_last_error()}); "
                      "input counts will be 0")
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                pass
            for h in hooks:
                if h:
                    user32.UnhookWindowsHookEx(h)

        self._hook_thread = threading.Thread(target=loop, name="input-hooks", daemon=True)
        self._hook_thread.start()
        ready.wait(2.0)

    def stop_input(self) -> None:
        if self._hook_tid:
            user32.PostThreadMessageW(self._hook_tid, WM_QUIT, 0, 0)
        if self._hook_thread:
            self._hook_thread.join(timeout=2.0)
