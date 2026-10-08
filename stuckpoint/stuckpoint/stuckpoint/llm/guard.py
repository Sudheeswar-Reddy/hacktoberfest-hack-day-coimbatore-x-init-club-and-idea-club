"""No-code guard (Person 2). Practice-mode hints must never contain code.

check_no_code(text) -> (ok, reason). Deliberately strict: a false "blocked" only
costs one regeneration; a leaked solution breaks the product's promise.
"""
from __future__ import annotations

import re

_CODE_LINE_PATTERNS = [
    (r"^\s*(def|class|import|from\s+\S+\s+import|return|elif|else\s*:|try\s*:|except\b|lambda\b)", "Python keyword"),
    (r"^\s*(public|private|static|void|int|long|bool|boolean|double|float|char|string|auto|const|let|var|function)\b[^.!?]*[;={(]", "C/Java/JS declaration"),
    (r"^\s*(for|while|if|switch)\s*\(", "C-style control statement"),
    (r"^\s*(for|while|if)\b[^.!?\n]*:\s*$", "Python control statement"),
    (r";\s*$", "statement terminator"),
    (r"=>", "arrow function"),
    (r"\b(vector|List|ArrayList|HashMap|unordered_map|Map)\s*<", "generic container type"),
    (r"\w+\[[^\]]*\]\s*(=|\+=|-=)(?!=)", "array/table assignment"),
    (r"\w+\s*(\+=|-=|\*=|//=)\s*\w", "compound assignment"),
    (r"\bprint\s*\(|\bconsole\.log\s*\(|\bSystem\.out\b|\bcout\s*<<", "output statement"),
    (r"\bmin\s*\([^)]*\+\s*1\s*\)", "solution recurrence written as code"),
    (r"^\s*[{}]\s*$", "lone brace"),
]


def check_no_code(text: str) -> tuple[bool, str | None]:
    """Return (True, None) if `text` looks code-free, else (False, reason)."""
    if not text:
        return True, None
    if "```" in text:
        return False, "contains a code block"
    for span in re.findall(r"`([^`]+)`", text):
        if len(span) > 20 or re.search(r"[=;(){}\[\]]", span):
            return False, "contains inline code"
    indented = [ln for ln in text.splitlines() if re.match(r"^( {4,}|\t)\S", ln)]
    if len(indented) > 2:
        return False, "contains an indented code block"
    for line in text.splitlines():
        for pattern, reason in _CODE_LINE_PATTERNS:
            if re.search(pattern, line):
                return False, f"contains code ({reason})"
    return True, None
