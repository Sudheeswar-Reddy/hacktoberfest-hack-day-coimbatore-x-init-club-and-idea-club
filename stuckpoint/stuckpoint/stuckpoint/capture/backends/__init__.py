"""Per-OS capture backends for capture/recorder.py.

Each backend exposes:
    foreground() -> Focus | None     focused app, window title, browser URL
    idle_seconds() -> float          seconds since the last user input
    start_input(cb) / stop_input()   cb(event_type, x, y) for 'key' and 'click'
"""
