"""Language server: pure helpers + a real stdio handshake."""
import json
import subprocess
import sys

from lsprotocol import types

from stuckpoint import lsp
from stuckpoint.models import CodeSuggestion

TEXT = "a = 1\nfor i in x:\n    for j in x:\n        pass\nprint(a)"


def _sug(replacement="better()"):
    return CodeSuggestion(id="sug-1", start_line=2, end_line=3, quote="", issue="Nested loop",
                          why="Slow.", complexity_before="O(n^2)", complexity_after="O(n)",
                          suggestion="Use a set.", replacement=replacement, confidence="high")


def _rng(a, b):
    return types.Range(start=types.Position(line=a, character=0), end=types.Position(line=b, character=0))


def test_diagnostics_cover_quoted_lines():
    [d] = lsp.to_diagnostics([_sug()], TEXT)
    assert (d.range.start.line, d.range.end.line, d.range.end.character) == (1, 2, len("    for j in x:"))
    assert d.severity == types.DiagnosticSeverity.Information and d.source == "StuckPoint"
    assert "O(n^2) → O(n)" in d.message


def test_hover_lookup():
    assert lsp.at_position([_sug()], 2).id == "sug-1"
    assert lsp.at_position([_sug()], 4) is None


def test_apply_quick_fix():
    [a] = lsp.code_actions("file:///x.py", [_sug()], TEXT, _rng(2, 2), "professional")
    edit = a.edit.changes["file:///x.py"][0]
    assert a.title.startswith("⚡ Apply") and edit.new_text == "better()"
    assert lsp.code_actions("file:///x.py", [_sug()], TEXT, _rng(4, 4), "professional") == []


def test_student_gets_show_me():
    [a] = lsp.code_actions("file:///x.py", [_sug(None)], TEXT, _rng(1, 1), "student")
    assert a.command.command == lsp.SHOW_ME and a.edit is None


def _frame(msg):
    body = json.dumps(msg).encode()
    return f"Content-Length: {len(body)}\r\n\r\n".encode() + body


def test_stdio_initialize_handshake():
    proc = subprocess.Popen([sys.executable, "-m", "stuckpoint", "lsp"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"processId": None, "rootUri": None, "capabilities": {},
                       "initializationOptions": {"profile": "student"}}}
    out, _ = proc.communicate(_frame(init) + _frame({"jsonrpc": "2.0", "id": 2, "method": "shutdown"})
                              + _frame({"jsonrpc": "2.0", "method": "exit"}), timeout=30)
    reply = json.loads(out.split(b"\r\n\r\n", 1)[1].split(b"Content-Length")[0])
    caps = reply["result"]["capabilities"]
    assert caps["hoverProvider"] and caps["codeActionProvider"]
    assert lsp.SHOW_ME in caps["executeCommandProvider"]["commands"]
