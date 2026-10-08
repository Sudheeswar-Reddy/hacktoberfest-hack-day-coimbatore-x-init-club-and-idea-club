// extension.js — StuckPoint VS Code Extension
// Tracks activity, shows diagnostics + hover cards + quick fixes for slow code

const vscode = require("vscode");

const ENGINE = "http://127.0.0.1:8765";

// ===== State =====
let diagnosticCollection;
let currentSuggestions = []; // [{start_line, end_line, issue, why, suggestion, replacement, ...}]
let inputCount = 0;
let trackingInterval = null;
let statusBarItem;

// ===== Activation =====
function activate(context) {
  console.log("StuckPoint extension activated");

  // Diagnostic collection (squiggle highlights)
  diagnosticCollection = vscode.languages.createDiagnosticCollection("StuckPoint");
  context.subscriptions.push(diagnosticCollection);

  // Status bar
  statusBarItem = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Left,
    100
  );
  statusBarItem.text = "$(zap) StuckPoint";
  statusBarItem.tooltip = "StuckPoint — click to review this file";
  statusBarItem.command = "stuckpoint.review";
  statusBarItem.show();
  context.subscriptions.push(statusBarItem);

  // ===== Commands =====
  context.subscriptions.push(
    vscode.commands.registerCommand("stuckpoint.review", () => {
      reviewCurrentFile();
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("stuckpoint.hint", () => {
      requestHint();
    })
  );

  // ===== Tracking: count text changes =====
  context.subscriptions.push(
    vscode.workspace.onDidChangeTextDocument((e) => {
      if (e.contentChanges.length > 0) {
        inputCount += e.contentChanges.length;
      }
    })
  );

  // ===== Send tracking events every 10s =====
  trackingInterval = setInterval(() => {
    if (vscode.window.state.focused) {
      sendTrackingEvents();
    }
  }, 10000);

  // ===== Review on save =====
  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument((doc) => {
      reviewFile(doc);
    })
  );

  // ===== Hover provider (GitHub-style hover card) =====
  context.subscriptions.push(
    vscode.languages.registerHoverProvider({ scheme: "file" }, {
      provideHover(document, position) {
        const line = position.line + 1; // 1-based

        const sug = currentSuggestions.find(
          (s) =>
            s._uri === document.uri.toString() &&
            line >= s.start_line &&
            line <= s.end_line
        );

        if (!sug) return null;

        const md = new vscode.MarkdownString();
        md.isTrusted = true;
        md.supportHtml = true;

        // Title with complexity
        let title = "**⚡ Faster approach**";
        if (sug.complexity_before && sug.complexity_after) {
          title += ` · \`${sug.complexity_before}\` → \`${sug.complexity_after}\``;
        }
        md.appendMarkdown(title + "\n\n");

        // Issue
        md.appendMarkdown(`🔴 **${sug.issue}**\n\n`);

        // Why
        md.appendMarkdown(`*${sug.why}*\n\n`);

        // Suggestion
        md.appendMarkdown(`**Try:** ${sug.suggestion}\n\n`);

        // Replacement code (only in project mode)
        if (sug.replacement) {
          md.appendMarkdown("---\n\n");
          md.appendMarkdown("**Faster version:**\n\n");
          md.appendCodeblock(sug.replacement, sug.language || "");
        }

        return new vscode.Hover(md);
      },
    })
  );

  // ===== Code action provider (⚡ Apply faster version) =====
  context.subscriptions.push(
    vscode.languages.registerCodeActionProvider(
      { scheme: "file" },
      {
        provideCodeActions(document, range) {
          const actions = [];

          for (const sug of currentSuggestions) {
            if (sug._uri !== document.uri.toString()) continue;
            if (!sug.replacement) continue;

            const sugRange = new vscode.Range(
              sug.start_line - 1,
              0,
              sug.end_line - 1,
              document.lineAt(Math.min(sug.end_line - 1, document.lineCount - 1)).text.length
            );

            // Only show if the cursor/selection overlaps the suggestion range
            if (!sugRange.intersection(range)) continue;

            const action = new vscode.CodeAction(
              `⚡ Apply faster version — ${sug.issue}`,
              vscode.CodeActionKind.QuickFix
            );

            action.edit = new vscode.WorkspaceEdit();
            action.edit.replace(document.uri, sugRange, sug.replacement);
            action.isPreferred = true;
            action.diagnostics = getDiagnosticsForSuggestion(document.uri, sug);

            actions.push(action);
          }

          return actions;
        },
      },
      { providedCodeActionKinds: [vscode.CodeActionKind.QuickFix] }
    )
  );

  // Initial status check
  checkEngineStatus();
}

// ===== Tracking =====
async function sendTrackingEvents() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) return;

  const doc = editor.document;
  const fileName = doc.fileName.split(/[/\\]/).pop();
  const workspace = vscode.workspace.name || "untitled";
  const ts = new Date().toISOString();

  const events = [
    {
      type: "focus",
      ts,
      app: "Code",
      title: `${fileName} — ${workspace}`,
      url: null,
    },
  ];

  if (inputCount > 0) {
    events.push({
      type: "input",
      ts,
      app: "Code",
      keys: inputCount,
      clicks: 0,
    });
    inputCount = 0;
  }

  try {
    await fetch(`${ENGINE}/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: "vscode", events }),
    });
  } catch {
    // Engine offline — silently ignore
  }
}

// ===== Review current file =====
async function reviewCurrentFile() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showInformationMessage("StuckPoint: Open a file to review.");
    return;
  }
  await reviewFile(editor.document);
}

async function reviewFile(doc) {
  const code = doc.getText();
  if (!code.trim()) return;

  const language = doc.languageId;
  const fileName = doc.fileName.split(/[/\\]/).pop();

  statusBarItem.text = "$(sync~spin) StuckPoint: Reviewing…";

  try {
    const res = await fetch(`${ENGINE}/suggest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code,
        language,
        problem_title: fileName,
        mode: "project",
        solved: false,
      }),
    });

    const data = await res.json();
    const sugs = data.suggestions || [];

    // Tag each suggestion with the document URI
    sugs.forEach((s) => {
      s._uri = doc.uri.toString();
      s.language = language;
    });

    // Replace suggestions for this file
    currentSuggestions = currentSuggestions.filter(
      (s) => s._uri !== doc.uri.toString()
    );
    currentSuggestions.push(...sugs);

    // Update diagnostics
    applyDiagnostics(doc.uri, sugs);

    statusBarItem.text = `$(zap) StuckPoint: ${sugs.length} suggestion${sugs.length !== 1 ? "s" : ""}`;

    if (sugs.length > 0) {
      vscode.window.showInformationMessage(
        `StuckPoint: Found ${sugs.length} faster approach${sugs.length !== 1 ? "es" : ""} — hover over highlighted lines.`
      );
    }
  } catch {
    statusBarItem.text = "$(zap) StuckPoint (offline)";
  }
}

// ===== Diagnostics (squiggle highlights) =====
function applyDiagnostics(uri, sugs) {
  const diagnostics = sugs.map((s) => {
    const range = new vscode.Range(
      s.start_line - 1,
      0,
      s.end_line - 1,
      1000
    );

    let message = `⚡ ${s.issue}`;
    if (s.complexity_before && s.complexity_after) {
      message += ` (${s.complexity_before} → ${s.complexity_after})`;
    }

    const diag = new vscode.Diagnostic(
      range,
      message,
      vscode.DiagnosticSeverity.Information
    );
    diag.source = "StuckPoint";
    diag.code = "perf";

    return diag;
  });

  diagnosticCollection.set(uri, diagnostics);
}

function getDiagnosticsForSuggestion(uri, sug) {
  const allDiags = diagnosticCollection.get(uri) || [];
  return allDiags.filter(
    (d) =>
      d.range.start.line === sug.start_line - 1 &&
      d.source === "StuckPoint"
  );
}

// ===== Hint =====
async function requestHint() {
  const editor = vscode.window.activeTextEditor;
  const fileName = editor
    ? editor.document.fileName.split(/[/\\]/).pop()
    : "unknown";

  try {
    const res = await fetch(`${ENGINE}/hint`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        problem_key: "project",
        problem_title: fileName,
        level: 1,
        context: "project",
        code: editor ? editor.document.getText() : "",
      }),
    });

    const data = await res.json();

    if (data.hint) {
      // Show hint in a nice panel
      const panel = vscode.window.createWebviewPanel(
        "stuckpointHint",
        "⚡ StuckPoint Hint",
        vscode.ViewColumn.Beside,
        { enableScripts: false }
      );

      panel.webview.html = getHintWebviewContent(data.hint, fileName);
    }
  } catch {
    vscode.window.showErrorMessage(
      "StuckPoint: Engine offline — run `python -m stuckpoint serve`"
    );
  }
}

function getHintWebviewContent(hint, fileName) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <style>
    body {
      font-family: 'Segoe UI', system-ui, sans-serif;
      padding: 24px;
      color: #cdd6f4;
      background: #1e1e2e;
      line-height: 1.6;
    }
    h1 {
      font-size: 18px;
      background: linear-gradient(135deg, #7c5cfc, #c084fc);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 6px;
    }
    .file { color: #9399b2; font-size: 13px; margin-bottom: 20px; }
    .hint-box {
      background: #11111b;
      border: 1px solid rgba(124, 92, 252, 0.2);
      border-radius: 8px;
      padding: 16px 20px;
      font-size: 14px;
      white-space: pre-wrap;
    }
  </style>
</head>
<body>
  <h1>⚡ StuckPoint Hint</h1>
  <div class="file">${escapeHtml(fileName)}</div>
  <div class="hint-box">${escapeHtml(hint)}</div>
</body>
</html>`;
}

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ===== Engine status check =====
async function checkEngineStatus() {
  try {
    const res = await fetch(`${ENGINE}/health`);
    const data = await res.json();
    if (data.ok) {
      statusBarItem.text = "$(zap) StuckPoint";
      statusBarItem.tooltip = `StuckPoint — connected (${data.model || "Gemma 4"})`;
    }
  } catch {
    statusBarItem.text = "$(zap) StuckPoint (offline)";
    statusBarItem.tooltip =
      "StuckPoint — engine offline. Run: python -m stuckpoint serve";
  }
}

// ===== Deactivation =====
function deactivate() {
  if (trackingInterval) clearInterval(trackingInterval);
  if (diagnosticCollection) diagnosticCollection.dispose();
}

module.exports = { activate, deactivate };
