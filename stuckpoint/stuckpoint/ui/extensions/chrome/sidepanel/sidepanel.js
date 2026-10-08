// sidepanel.js — StuckPoint side panel logic
(function () {
  const ENGINE = "http://127.0.0.1:8765";
  let currentSignal = null;
  let hintLevel = 0;
  let currentContext = "unknown";
  let pollTimer = null;

  // ===== Tab switching =====
  const tabs = document.querySelectorAll(".tab");
  const sections = document.querySelectorAll(".tab-content");

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((t) => t.classList.remove("active"));
      sections.forEach((s) => s.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById(tab.dataset.tab).classList.add("active");
    });
  });

  // ===== Engine communication =====
  async function engineFetch(path, options = {}) {
    try {
      const res = await fetch(`${ENGINE}${path}`, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });
      document.getElementById("engine-offline").classList.add("hidden");
      return await res.json();
    } catch {
      document.getElementById("engine-offline").classList.remove("hidden");
      return null;
    }
  }

  // ===== Poll /status =====
  async function pollStatus() {
    const data = await engineFetch("/status");
    if (!data) return;

    // Update context badge
    currentContext = data.context || "unknown";
    const badge = document.getElementById("context-badge");
    badge.className = "badge";

    const contextMap = {
      practice: { cls: "badge--practice", text: "🟢 Practice" },
      project:  { cls: "badge--project",  text: "🔵 Project" },
      exam:     { cls: "badge--exam",     text: "⛔ Exam — StuckPoint is off" },
    };

    const ctx = contextMap[currentContext] || { cls: "badge--unknown", text: "🔍 Detecting…" };
    badge.classList.add(ctx.cls);

    // Add problem name if available
    let label = ctx.text;
    if (data.problem) label += ` — ${data.problem}`;
    badge.textContent = label;

    // Show/hide project area
    const projectArea = document.getElementById("project-area");
    if (currentContext === "project") {
      projectArea.classList.remove("hidden");
    } else {
      projectArea.classList.add("hidden");
    }

    // Show/hide practice notice
    const practiceNotice = document.getElementById("practice-notice");
    if (currentContext === "practice") {
      practiceNotice.classList.remove("hidden");
    } else {
      practiceNotice.classList.add("hidden");
    }

    // Stuck signal
    const stuckCard = document.getElementById("stuck-card");
    if (data.signal && (!currentSignal || currentSignal.id !== data.signal.id)) {
      currentSignal = data.signal;
      hintLevel = 0;
      document.getElementById("stuck-detail").textContent =
        data.signal.reason || "You seem stuck. Want a hint?";
      stuckCard.classList.remove("hidden");
      document.getElementById("hint-area").classList.add("hidden");
    }
  }

  // ===== Hint flow =====
  document.getElementById("btn-hint").addEventListener("click", async () => {
    document.getElementById("stuck-card").classList.add("hidden");
    document.getElementById("hint-area").classList.remove("hidden");
    if (currentSignal) {
      await engineFetch(`/signal/${currentSignal.id}/status`, {
        method: "POST",
        body: JSON.stringify({ status: "accepted" }),
      });
    }
    requestHint();
  });

  document.getElementById("btn-next-hint").addEventListener("click", () => {
    requestHint();
  });

  async function requestHint() {
    hintLevel++;
    const payload = {
      problem_key: currentSignal?.problem_key || "unknown",
      problem_title: currentSignal?.problem || "Unknown",
      level: hintLevel,
      context: currentContext,
    };

    const data = await engineFetch("/hint", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    if (data && data.hint) {
      const list = document.getElementById("hints-list");
      const bubble = document.createElement("div");
      bubble.className = "hint-bubble";
      bubble.innerHTML = `
        <div class="hint-level">Hint ${hintLevel}</div>
        <div>${escapeHtml(data.hint)}</div>
      `;
      list.appendChild(bubble);

      // Hide "Next hint" after level 3
      if (hintLevel >= 3) {
        document.getElementById("btn-next-hint").classList.add("hidden");
      }
    }
  }

  // ===== Snooze / Dismiss =====
  document.getElementById("btn-snooze").addEventListener("click", async () => {
    if (currentSignal) {
      await engineFetch(`/signal/${currentSignal.id}/status`, {
        method: "POST",
        body: JSON.stringify({ status: "snoozed" }),
      });
    }
    document.getElementById("stuck-card").classList.add("hidden");
    currentSignal = null;
  });

  document.getElementById("btn-dismiss").addEventListener("click", async () => {
    if (currentSignal) {
      await engineFetch(`/signal/${currentSignal.id}/status`, {
        method: "POST",
        body: JSON.stringify({ status: "dismissed" }),
      });
    }
    document.getElementById("stuck-card").classList.add("hidden");
    currentSignal = null;
  });

  // ===== Solved =====
  document.getElementById("btn-solved").addEventListener("click", async () => {
    if (currentSignal) {
      await engineFetch("/solved", {
        method: "POST",
        body: JSON.stringify({
          problem_key: currentSignal.problem_key || "unknown",
          solved: true,
        }),
      });

      // Also save in chrome.storage for editor_ui.js
      if (typeof chrome !== "undefined" && chrome.storage) {
        chrome.storage.local.get("solvedProblems", (data) => {
          const map = data.solvedProblems || {};
          map[currentSignal.problem || "unknown"] = true;
          chrome.storage.local.set({ solvedProblems: map });
        });
      }
    }

    document.getElementById("hint-area").classList.add("hidden");
    currentSignal = null;
    hintLevel = 0;
  });

  // ===== Project help =====
  document.getElementById("btn-project-hint").addEventListener("click", async () => {
    const code = document.getElementById("project-input").value;
    if (!code.trim()) return;

    const data = await engineFetch("/hint", {
      method: "POST",
      body: JSON.stringify({
        problem_key: "project",
        problem_title: "Project code",
        level: 1,
        context: "project",
        code,
      }),
    });

    if (data && data.hint) {
      const output = document.getElementById("full-fix-output");
      output.textContent = data.hint;
      output.classList.remove("hidden");
    }
  });

  document.getElementById("btn-full-fix").addEventListener("click", async () => {
    const code = document.getElementById("project-input").value;
    if (!code.trim()) return;

    const data = await engineFetch("/help/full", {
      method: "POST",
      body: JSON.stringify({
        problem_key: "project",
        problem_title: "Project code",
        level: 4,
        context: "project",
        code,
      }),
    });

    if (data && data.hint) {
      const output = document.getElementById("full-fix-output");
      output.textContent = data.hint;
      output.classList.remove("hidden");
    } else if (data && data.error) {
      const output = document.getElementById("full-fix-output");
      output.textContent = `Error: ${data.error}`;
      output.classList.remove("hidden");
    }
  });

  // ===== Suggestions tab =====
  // Listens for suggestion updates from background
  if (typeof chrome !== "undefined" && chrome.runtime) {
    chrome.runtime.onMessage.addListener((msg) => {
      if (msg.type === "sp-suggestions-update") {
        renderSuggestions(msg.suggestions || []);
      }
    });
  }

  function renderSuggestions(sugs) {
    const list = document.getElementById("sug-list");
    if (!sugs.length) {
      list.innerHTML = '<p class="empty-state">No suggestions yet. Write some code and they\'ll appear here.</p>';
      return;
    }

    list.innerHTML = sugs
      .map((s) => {
        let html = `<div class="sug-card">`;
        html += `<div class="sug-issue">⚡ ${escapeHtml(s.issue)}</div>`;
        if (s.complexity_before && s.complexity_after) {
          html += `<div class="sug-complexity">${escapeHtml(s.complexity_before)} → ${escapeHtml(s.complexity_after)}</div>`;
        }
        html += `<div class="sug-text">${escapeHtml(s.suggestion)}</div>`;
        if (s.replacement) {
          html += `<pre class="code-block">${escapeHtml(s.replacement)}</pre>`;
        }
        html += `</div>`;
        return html;
      })
      .join("");
  }

  // ===== Report tab =====
  document.getElementById("btn-refresh-report").addEventListener("click", async () => {
    const data = await engineFetch("/report");
    if (!data) return;
    renderReport(data);
  });

  function renderReport(data) {
    const container = document.getElementById("report-content");

    let html = "";

    // Headline numbers
    if (data.metrics && data.metrics.overall) {
      const o = data.metrics.overall;
      html += `<div class="headline-numbers">
        <div class="headline-stat"><div class="stat-value">${o.problems || 0}</div><div class="stat-label">Problems</div></div>
        <div class="headline-stat"><div class="stat-value">${(o.total_active_min || 0).toFixed(0)}m</div><div class="stat-label">Active Time</div></div>
        <div class="headline-stat"><div class="stat-value">${o.stuck_episodes || 0}</div><div class="stat-label">Stuck Episodes</div></div>
        <div class="headline-stat"><div class="stat-value">${o.hints_used || 0}</div><div class="stat-label">Hints Used</div></div>
      </div>`;
    }

    // Gate summary
    if (data.gate_summary) {
      const g = data.gate_summary;
      html += `<div class="gate-summary">
        <span class="gate-pill gate-pill--passed">✓ ${g.passed || 0} verified</span>
        <span class="gate-pill gate-pill--degraded">⚠ ${g.downgraded || 0} low-confidence</span>
        <span class="gate-pill gate-pill--rejected">✗ ${g.rejected || 0} rejected</span>
      </div>`;
    }

    // Claims
    if (data.claims && data.claims.length) {
      data.claims.forEach((c, i) => {
        const isRejected = c.gate_outcome === "rejected";
        const badgeCls =
          c.gate_outcome === "passed"
            ? "claim-badge--verified"
            : c.gate_outcome === "downgraded"
            ? "claim-badge--low"
            : "claim-badge--rejected";
        const badgeText =
          c.gate_outcome === "passed"
            ? "Verified ✓"
            : c.gate_outcome === "downgraded"
            ? "Low confidence ⚠"
            : "Rejected ✗";

        html += `<div class="claim-card ${isRejected ? "claim-card--rejected" : ""}">
          <span class="claim-badge ${badgeCls}">${badgeText}</span>
          <div class="claim-text">${escapeHtml(c.text || c.claim || "")}</div>
          ${isRejected && c.gate_reason ? `<div class="claim-reason">${escapeHtml(c.gate_reason)}</div>` : ""}
          <button class="evidence-toggle" data-idx="${i}">Show evidence</button>
          <div class="claim-evidence" id="evidence-${i}">${escapeHtml(JSON.stringify(c.evidence || c.numeric_claims || {}, null, 2))}</div>
        </div>`;
      });
    } else {
      html += '<p class="empty-state">No claims available yet.</p>';
    }

    container.innerHTML = html;

    // Wire evidence toggles
    container.querySelectorAll(".evidence-toggle").forEach((btn) => {
      btn.addEventListener("click", () => {
        const ev = document.getElementById(`evidence-${btn.dataset.idx}`);
        const isOpen = ev.classList.toggle("open");
        btn.textContent = isOpen ? "Hide evidence" : "Show evidence";
      });
    });
  }

  // ===== Utility =====
  function escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // ===== Start polling =====
  pollStatus();
  pollTimer = setInterval(pollStatus, 5000);
})();
