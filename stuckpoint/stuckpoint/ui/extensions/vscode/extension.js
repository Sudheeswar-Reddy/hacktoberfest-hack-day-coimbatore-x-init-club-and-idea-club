// extension.js — StuckPoint VS Code Extension
// Full autonomous side panel (Copilot-style) + live squiggly diagnostics + hover cards + quick fixes

const vscode = require("vscode");
const fs = require("fs");
const path = require("path");

const ENGINE = "http://127.0.0.1:8765";

// ===== Extension State =====
let diagnosticCollection;
let currentSuggestions = []; // [{start_line, end_line, issue, why, suggestion, replacement, ...}]
let inputCount = 0;
let trackingInterval = null;
let statusPollInterval = null;
let debounceTimer = null;
let statusBarItem;
let sidePanelProvider;

// ===== Activation =====
function activate(context) {
  console.log("[StuckPoint] Extension activating...");

  // 1. Diagnostics collection
  diagnosticCollection = vscode.languages.createDiagnosticCollection("StuckPoint");
  context.subscriptions.push(diagnosticCollection);

  // 2. Status bar item
  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  statusBarItem.text = "$(zap) StuckPoint";
  statusBarItem.tooltip = "StuckPoint Assistant — Click to focus sidebar";
  statusBarItem.command = "stuckpoint.focusSidePanel";
  statusBarItem.show();
  context.subscriptions.push(statusBarItem);

  // 3. Register Side Panel Provider (WebviewView)
  sidePanelProvider = new StuckPointSidePanelProvider(context.extensionUri);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider("stuckpoint.sidepanel", sidePanelProvider, {
      webviewOptions: { retainContextWhenHidden: true },
    })
  );

  // 4. Commands
  context.subscriptions.push(
    vscode.commands.registerCommand("stuckpoint.review", () => {
      reviewCurrentFile();
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("stuckpoint.hint", () => {
      sidePanelProvider.requestHint();
      vscode.commands.executeCommand("stuckpoint.sidepanel.focus");
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("stuckpoint.focusSidePanel", () => {
      vscode.commands.executeCommand("stuckpoint.sidepanel.focus");
    })
  );

  // 5. Autonomous Typing Tracker & Real-Time Review (2s debounce)
  context.subscriptions.push(
    vscode.workspace.onDidChangeTextDocument((e) => {
      if (e.contentChanges.length > 0) {
        inputCount += e.contentChanges.length;

        const config = vscode.workspace.getConfiguration("stuckpoint");
        if (config.get("autoReview", true)) {
          clearTimeout(debounceTimer);
          debounceTimer = setTimeout(() => {
            reviewFile(e.document);
          }, 2000);
        }
      }
    })
  );

  // 6. Review on active editor change or save
  context.subscriptions.push(
    vscode.window.onDidChangeActiveTextEditor((editor) => {
      if (editor && editor.document) {
        reviewFile(editor.document);
      }
    })
  );

  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument((doc) => {
      reviewFile(doc);
    })
  );

  // 7. Background Event Heartbeat (every 10s)
  trackingInterval = setInterval(() => {
    if (vscode.window.state.focused) {
      sendTrackingEvents();
    }
  }, 10000);

  // 8. Background Status Polling (every 5s autonomous)
  statusPollInterval = setInterval(() => {
    checkEngineStatusAndSignal();
  }, 5000);

  // 9. Hover Provider (GitHub-style hover cards)
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

        let title = "**⚡ Faster approach**";
        if (sug.complexity_before && sug.complexity_after) {
          title += ` · \`${sug.complexity_before}\` → \`${sug.complexity_after}\``;
        }
        md.appendMarkdown(title + "\n\n");
        md.appendMarkdown(`🔴 **${sug.issue}**\n\n`);
        md.appendMarkdown(`*${sug.why}*\n\n`);
        md.appendMarkdown(`**Try:** ${sug.suggestion}\n\n`);

        const config = vscode.workspace.getConfiguration("stuckpoint");
        const profile = config.get("profile", "professional");

        if (profile === "student" && !sug._unlocked) {
          md.appendMarkdown(`_💡 Learner mode: Mark problem solved or click in StuckPoint panel to view code._\n\n`);
        } else if (sug.replacement) {
          md.appendMarkdown("---\n\n");
          md.appendMarkdown("**Faster version:**\n\n");
          md.appendCodeblock(sug.replacement, sug.language || "");
        }

        return new vscode.Hover(md);
      },
    })
  );

  // 10. Code Action Provider (⚡ Apply faster version quick-fix)
  context.subscriptions.push(
    vscode.languages.registerCodeActionsProvider(
      { scheme: "file" },
      {
        provideCodeActions(document, range) {
          const actions = [];
          for (const sug of currentSuggestions) {
            if (sug._uri !== document.uri.toString() || !sug.replacement) continue;

            const sugRange = new vscode.Range(
              sug.start_line - 1,
              0,
              sug.end_line - 1,
              document.lineAt(Math.min(sug.end_line - 1, document.lineCount - 1)).text.length
            );

            if (!sugRange.intersection(range)) continue;

            const action = new vscode.CodeAction(
              `⚡ Apply faster version — ${sug.issue}`,
              vscode.CodeActionKind.QuickFix
            );
            action.edit = new vscode.WorkspaceEdit();
            action.edit.replace(document.uri, sugRange, sug.replacement);
            action.isPreferred = true;
            actions.push(action);
          }
          return actions;
        },
      },
      { providedCodeActionKinds: [vscode.CodeActionKind.QuickFix] }
    )
  );

  // Initial review
  if (vscode.window.activeTextEditor) {
    reviewFile(vscode.window.activeTextEditor.document);
  }
  checkEngineStatusAndSignal();
}

function deactivate() {
  if (trackingInterval) clearInterval(trackingInterval);
  if (statusPollInterval) clearInterval(statusPollInterval);
  if (debounceTimer) clearTimeout(debounceTimer);
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
    // Engine offline — ignore
  }
}

// ===== Autonomous Status & Stuck Signal Polling =====
async function checkEngineStatusAndSignal() {
  try {
    const res = await fetch(`${ENGINE}/status`);
    if (!res.ok) throw new Error("status error");
    const data = await res.json();

    const sugCount = currentSuggestions.length;
    const hasSignal = data.signal && data.signal.status !== "dismissed" && data.signal.status !== "snoozed";

    // Update status bar icon & color to reflect stuck state
    if (hasSignal) {
      // Amber warning icon when stuck detected
      statusBarItem.text = `$(warning) StuckPoint — Stuck Detected`;
      statusBarItem.backgroundColor = new vscode.ThemeColor("statusBarItem.warningBackground");
    } else if (sugCount > 0) {
      statusBarItem.text = `$(zap) StuckPoint: ${sugCount} suggestion${sugCount !== 1 ? "s" : ""}`;
      statusBarItem.backgroundColor = undefined;
    } else {
      statusBarItem.text = `$(zap) StuckPoint`;
      statusBarItem.backgroundColor = undefined;
    }

    if (sidePanelProvider) {
      sidePanelProvider.updateEngineStatus(true, data.context || "project", data.signal);
    }
  } catch {
    statusBarItem.text = "$(error) StuckPoint (offline)";
    statusBarItem.backgroundColor = new vscode.ThemeColor("statusBarItem.errorBackground");
    if (sidePanelProvider) {
      sidePanelProvider.updateEngineStatus(false, "offline", null);
    }
  }
}

// ===== Code Review =====
async function reviewCurrentFile() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showInformationMessage("StuckPoint: Open a code file to review.");
    return;
  }
  await reviewFile(editor.document);
}

async function reviewFile(doc) {
  if (!doc || doc.isClosed || doc.uri.scheme !== "file") return;
  const code = doc.getText();
  if (!code.trim()) return;

  const language = doc.languageId;
  const fileName = doc.fileName.split(/[/\\]/).pop();
  const config = vscode.workspace.getConfiguration("stuckpoint");
  const profile = config.get("profile", "professional");

  try {
    const res = await fetch(`${ENGINE}/suggest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code,
        language,
        problem_title: fileName,
        mode: "project",
        profile,
        surface: "ide",
        solved: false,
      }),
    });

    if (!res.ok) throw new Error("suggest error");
    const data = await res.json();
    const sugs = data.suggestions || [];

    sugs.forEach((s) => {
      s._uri = doc.uri.toString();
      s.language = language;
    });

    currentSuggestions = currentSuggestions.filter((s) => s._uri !== doc.uri.toString());
    currentSuggestions.push(...sugs);

    applyDiagnostics(doc.uri, sugs);

    if (sidePanelProvider) {
      sidePanelProvider.updateSuggestions(currentSuggestions, fileName);
    }

    statusBarItem.text = `$(zap) StuckPoint: ${sugs.length} suggestion${sugs.length !== 1 ? "s" : ""}`;
  } catch {
    // Engine offline
  }
}

function applyDiagnostics(uri, sugs) {
  const diagnostics = sugs.map((s) => {
    const range = new vscode.Range(
      Math.max(0, s.start_line - 1),
      0,
      Math.max(0, s.end_line - 1),
      1000
    );

    let message = `⚡ ${s.issue}`;
    if (s.complexity_before && s.complexity_after) {
      message += ` (${s.complexity_before} → ${s.complexity_after})`;
    }

    const diag = new vscode.Diagnostic(range, message, vscode.DiagnosticSeverity.Information);
    diag.source = "StuckPoint";
    diag.code = "perf";
    return diag;
  });

  diagnosticCollection.set(uri, diagnostics);
}

// ===== Apply Code Suggestion Directly to Active Editor =====
async function applySuggestionToEditor(sug) {
  const editor = vscode.window.activeTextEditor;
  if (!editor || !sug.replacement) return;

  const range = new vscode.Range(
    sug.start_line - 1,
    0,
    sug.end_line - 1,
    editor.document.lineAt(Math.min(sug.end_line - 1, editor.document.lineCount - 1)).text.length
  );

  await editor.edit((editBuilder) => {
    editBuilder.replace(range, sug.replacement);
  });

  vscode.window.showInformationMessage(`⚡ Applied: ${sug.issue}`);
  reviewFile(editor.document);
}

// ===== Copilot-Style WebviewViewProvider for Activity Bar =====
class StuckPointSidePanelProvider {
  constructor(extensionUri) {
    this._extensionUri = extensionUri;
    this._view = null;
    this._engineOnline = false;
    this._context = "project";
    this._signal = null;
    this._suggestions = [];
    this._fileName = "";
    this._hintLevel = 0;
  }

  resolveWebviewView(webviewView) {
    this._view = webviewView;

    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this._extensionUri],
    };

    webviewView.webview.html = this._getHtmlForWebview();

    webviewView.webview.onDidReceiveMessage(async (msg) => {
      switch (msg.type) {
        case "request_hint":
          this.requestHint();
          break;
        case "snooze_signal":
          await this._updateSignalStatus("snoozed");
          break;
        case "dismiss_signal":
          await this._updateSignalStatus("dismissed");
          break;
        case "mark_solved":
          await this._markSolved();
          break;
        case "project_help":
          await this._projectHelp(msg.query, msg.full);
          break;
        case "apply_suggestion":
          if (msg.index !== undefined && this._suggestions[msg.index]) {
            applySuggestionToEditor(this._suggestions[msg.index]);
          }
          break;
        case "fetch_report":
          await this._fetchReport();
          break;
        case "trigger_review":
          reviewCurrentFile();
          break;
      }
    });

    // Send initial state to webview
    this._syncState();
  }

  updateEngineStatus(online, context, signal) {
    this._engineOnline = online;
    this._context = context;
    this._signal = signal;
    this._syncState();
  }

  updateSuggestions(suggestions, fileName) {
    this._suggestions = suggestions;
    this._fileName = fileName;
    this._syncState();
  }

  _syncState() {
    if (!this._view) return;
    this._view.webview.postMessage({
      type: "state_update",
      online: this._engineOnline,
      context: this._context,
      signal: this._signal,
      suggestions: this._suggestions,
      fileName: this._fileName,
      hintLevel: this._hintLevel,
    });
  }

  async requestHint() {
    this._hintLevel = Math.min(this._hintLevel + 1, 3);
    const editor = vscode.window.activeTextEditor;
    const fileName = editor ? editor.document.fileName.split(/[/\\]/).pop() : "active file";
    const code = editor ? editor.document.getText() : "";

    try {
      const res = await fetch(`${ENGINE}/hint`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          problem_key: "project",
          problem_title: fileName,
          level: this._hintLevel,
          context: this._context,
          code,
        }),
      });
      const data = await res.json();
      if (this._view) {
        this._view.webview.postMessage({
          type: "hint_received",
          hint: data.hint,
          level: this._hintLevel,
        });
      }
    } catch {
      // offline
    }
  }

  async _projectHelp(query, full) {
    const editor = vscode.window.activeTextEditor;
    const code = editor ? editor.document.getText() : "";

    try {
      const endpoint = full ? `${ENGINE}/help/full` : `${ENGINE}/hint`;
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          problem_key: "project",
          problem_title: this._fileName || "Current File",
          level: 4,
          context: "project",
          code: query || code,
        }),
      });
      const data = await res.json();
      if (this._view) {
        this._view.webview.postMessage({
          type: "project_help_received",
          text: data.code || data.hint,
          isCode: full,
        });
      }
    } catch {
      // offline
    }
  }

  async _updateSignalStatus(status) {
    if (!this._signal) return;
    try {
      await fetch(`${ENGINE}/signal/${this._signal.id}/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      this._signal = null;
      this._syncState();
    } catch {}
  }

  async _markSolved() {
    try {
      await fetch(`${ENGINE}/solved`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ problem_key: this._fileName || "project", solved: true }),
      });
      if (this._view) {
        this._view.webview.postMessage({ type: "solved_success" });
      }
    } catch {}
  }

  async _fetchReport() {
    try {
      const res = await fetch(`${ENGINE}/report`);
      const report = await res.json();
      if (this._view) {
        this._view.webview.postMessage({ type: "report_data", report });
      }
    } catch {}
  }

  _getHtmlForWebview() {
    // Generate cryptographically random nonce for CSP compliance
    const nonce = require("crypto").randomBytes(16).toString("base64");

    const htmlPath = path.join(__dirname, "sidepanel.html");
    let html = fs.readFileSync(htmlPath, "utf8");

    // Replace nonce placeholders in CSP meta tag and inline script/style
    html = html
      .replace(/\{\{NONCE\}\}/g, nonce)
      .replace(/\{\{NONCE_STYLE\}\}/g, `'nonce-${nonce}'`)
      .replace(/\{\{NONCE_SCRIPT\}\}/g, `'nonce-${nonce}'`);

    return html;
  }
}

module.exports = {
  activate,
  deactivate,
};
