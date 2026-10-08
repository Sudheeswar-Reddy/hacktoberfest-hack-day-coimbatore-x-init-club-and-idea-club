"""StuckPoint language server (Person 2): the same highlights and hover cards in ANY editor.

    python -m stuckpoint lsp            (stdio)

One server gives every LSP client what the VS Code extension gives VS Code:
Neovim, JetBrains (LSP4IJ plugin), Sublime Text (LSP package), Zed, Helix, Emacs (eglot)...

  didOpen / didSave  -> suggest(surface="ide") -> Information diagnostics (the highlight)
  hover              -> the same markdown card as everywhere else
  codeAction         -> "⚡ Apply faster version" (WorkspaceEdit), or in the student profile
                        "⚡ Show me the faster code" (re-runs with solved=true)

Profile: initializationOptions {"profile": "student"} or $STUCKPOINT_PROFILE (default professional).
Runs in-process (no engine needed); it reads GEMINI_API_KEY from .env like everything else.
"""
from __future__ import annotations

import asyncio
import os
from typing import Optional

from lsprotocol import types
from pygls.lsp.server import LanguageServer

from .llm.suggest import card_markdown, suggest_with_stats
from .models import CodeSuggestion

SOURCE = "StuckPoint"
SHOW_ME = "stuckpoint.showMe"


class StuckPointServer(LanguageServer):
    def __init__(self):
        super().__init__("stuckpoint", "0.2.0")
        self.profile = os.getenv("STUCKPOINT_PROFILE", "professional")
        self.results: dict[str, list[CodeSuggestion]] = {}   # uri -> current suggestions
        self.languages: dict[str, str] = {}
        self.unlocked: set[str] = set()                      # uris where the student clicked "Show me"


server = StuckPointServer()


# ---- pure helpers (unit-tested without an editor) ---------------------------
def line_range(s: CodeSuggestion, lines: list[str]) -> types.Range:
    end_idx = min(s.end_line, len(lines)) - 1
    return types.Range(start=types.Position(line=s.start_line - 1, character=0),
                       end=types.Position(line=end_idx, character=len(lines[end_idx]) if lines else 0))


def to_diagnostics(sugs: list[CodeSuggestion], text: str) -> list[types.Diagnostic]:
    lines = text.splitlines() or [""]
    out = []
    for s in sugs:
        msg = s.issue
        if s.complexity_before and s.complexity_after:
            msg += f" ({s.complexity_before} → {s.complexity_after})"
        out.append(types.Diagnostic(range=line_range(s, lines), message=msg, source=SOURCE,
                                    severity=types.DiagnosticSeverity.Information,
                                    code=s.id))
    return out


def at_position(sugs: list[CodeSuggestion], line0: int) -> Optional[CodeSuggestion]:
    for s in sugs:
        if s.start_line - 1 <= line0 <= s.end_line - 1:
            return s
    return None


def code_actions(uri: str, sugs: list[CodeSuggestion], text: str,
                 rng: types.Range, profile: str) -> list[types.CodeAction]:
    lines = text.splitlines() or [""]
    out = []
    for s in sugs:
        if s.end_line - 1 < rng.start.line or s.start_line - 1 > rng.end.line:
            continue
        if s.replacement:
            edit = types.TextEdit(range=line_range(s, lines), new_text=s.replacement)
            out.append(types.CodeAction(
                title="⚡ Apply faster version", kind=types.CodeActionKind.QuickFix,
                edit=types.WorkspaceEdit(changes={uri: [edit]}), is_preferred=True))
        elif profile == "student":
            out.append(types.CodeAction(
                title="⚡ Show me the faster code", kind=types.CodeActionKind.QuickFix,
                command=types.Command(title="Show me", command=SHOW_ME, arguments=[uri])))
    return out


# ---- LSP handlers -------------------------------------------------------------
async def review(ls: StuckPointServer, uri: str) -> None:
    doc = ls.workspace.get_text_document(uri)
    language = ls.languages.get(uri, "")
    _, sugs, _ = await asyncio.to_thread(
        suggest_with_stats, doc.source, language, None, "ide", ls.profile,
        uri in ls.unlocked, os.path.basename(doc.path or uri))
    ls.results[uri] = sugs
    ls.text_document_publish_diagnostics(types.PublishDiagnosticsParams(
        uri=uri, diagnostics=to_diagnostics(sugs, doc.source), version=doc.version))


@server.feature(types.INITIALIZE)
def on_initialize(ls: StuckPointServer, params: types.InitializeParams):
    opts = params.initialization_options or {}
    if isinstance(opts, dict) and opts.get("profile") in ("professional", "student"):
        ls.profile = opts["profile"]


@server.feature(types.TEXT_DOCUMENT_DID_OPEN)
async def did_open(ls: StuckPointServer, params: types.DidOpenTextDocumentParams):
    ls.languages[params.text_document.uri] = params.text_document.language_id
    await review(ls, params.text_document.uri)


@server.feature(types.TEXT_DOCUMENT_DID_SAVE)
async def did_save(ls: StuckPointServer, params: types.DidSaveTextDocumentParams):
    await review(ls, params.text_document.uri)


@server.feature(types.TEXT_DOCUMENT_DID_CLOSE)
def did_close(ls: StuckPointServer, params: types.DidCloseTextDocumentParams):
    ls.results.pop(params.text_document.uri, None)


@server.feature(types.TEXT_DOCUMENT_HOVER)
def hover(ls: StuckPointServer, params: types.HoverParams) -> Optional[types.Hover]:
    uri = params.text_document.uri
    s = at_position(ls.results.get(uri, []), params.position.line)
    if s is None:
        return None
    md = card_markdown(s, ls.languages.get(uri, ""))
    if not s.replacement and ls.profile == "student":
        md += "\n\n_Use the quick fix **Show me the faster code** when you're ready._"
    lines = ls.workspace.get_text_document(uri).source.splitlines() or [""]
    return types.Hover(contents=types.MarkupContent(kind=types.MarkupKind.Markdown, value=md),
                       range=line_range(s, lines))


@server.feature(types.TEXT_DOCUMENT_CODE_ACTION,
                types.CodeActionOptions(code_action_kinds=[types.CodeActionKind.QuickFix]))
def code_action(ls: StuckPointServer, params: types.CodeActionParams):
    uri = params.text_document.uri
    text = ls.workspace.get_text_document(uri).source
    return code_actions(uri, ls.results.get(uri, []), text, params.range, ls.profile)


@server.command(SHOW_ME)
async def show_me(ls: StuckPointServer, uri: str):
    ls.unlocked.add(uri)
    await review(ls, uri)


def main() -> None:
    server.start_io()
