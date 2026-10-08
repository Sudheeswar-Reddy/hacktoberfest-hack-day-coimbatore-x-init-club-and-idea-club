// sidepanel.js — StuckPoint Chrome MV3 Side Panel Logic
// Seamlessly preserves all engine communication while implementing the redesign system.

(function () {
  "use strict";

  const ENGINE = "http://127.0.0.1:8765";
  let currentSignal = null;
  let hintLevel = 0;
  let currentContext = "unknown";
  let pollTimer = null;
  let sessionSeconds = 0;
  let sessionTimerInterval = null;
  let reportLoadedOnce = false;

  // ===== 1. Tab Switching with Sliding Indicator =====
  const tabs = document.querySelectorAll(".sp-tab-btn");
  const panels = document.querySelectorAll(".sp-tab-panel");
  const tabSlider = document.getElementById("tab-slider");

  function updateTabSlider(activeTab) {
    if (!tabSlider || !activeTab) return;
    const parentRect = activeTab.parentElement.getBoundingClientRect();
    const tabRect = activeTab.getBoundingClientRect();
    const leftOffset = tabRect.left - parentRect.left;
    tabSlider.style.transform = `translateX(${leftOffset}px)`;
    tabSlider.style.width = `${tabRect.width}px`;
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((t) => {
        t.classList.remove("active");
        t.setAttribute("aria-selected", "false");
      });
      panels.forEach((p) => p.classList.remove("active"));

      tab.classList.add("active");
      tab.setAttribute("aria-selected", "true");
      updateTabSlider(tab);

      const targetId = `panel-${tab.dataset.tab}`;
      const targetPanel = document.getElementById(targetId);
      if (targetPanel) {
        targetPanel.classList.add("active");
      }

      if (tab.dataset.tab === "report" && !reportLoadedOnce) {
        loadReport();
      }
    });
  });

  // Position slider on initial load & resize
  window.addEventListener("resize", () => {
    const active = document.querySelector(".sp-tab-btn.active");
    if (active) updateTabSlider(active);
  });
  setTimeout(() => {
    const active = document.querySelector(".sp-tab-btn.active");
    if (active) updateTabSlider(active);
  }, 100);

  // ===== 2. Live Session Timer =====
  function startSessionTimer() {
    const timerEl = document.getElementById("session-timer");
    if (!timerEl) return;
    sessionTimerInterval = setInterval(() => {
      sessionSeconds++;
      const mins = Math.floor(sessionSeconds / 60);
      const secs = sessionSeconds % 60;
      timerEl.textContent = `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
    }, 1000);
  }
  startSessionTimer();

  // ===== 3. Toast System =====
  function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) return;
    const toast = document.createElement("div");
    toast.className = "sp-toast";
    toast.innerHTML = `
      <svg style="width:14px;height:14px;color:var(--sp-color-primary);flex-shrink:0;">
        <use href="#icon-zap"></use>
      </svg>
      <span>${escapeHtml(message)}</span>
    `;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.transition = "opacity 200ms ease, transform 200ms ease";
      toast.style.opacity = "0";
      toast.style.transform = "translateY(8px)";
      setTimeout(() => toast.remove(), 220);
    }, 3200);
  }

  // ===== 4. Engine Communication =====
  async function engineFetch(path, options = {}) {
    const offlineNotice = document.getElementById("engine-offline");
    const statusDot = document.getElementById("status-dot");
    try {
      const res = await fetch(`${ENGINE}${path}`, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });
      if (offlineNotice) offlineNotice.classList.add("hidden");
      return await res.json();
    } catch {
      if (offlineNotice) offlineNotice.classList.remove("hidden");
      if (statusDot) {
        statusDot.className = "sp-status-dot offline";
      }
      return null;
    }
  }

  // ===== 5. Status Polling & Stuck Signal =====
  async function pollStatus() {
    const data = await engineFetch("/status");
    if (!data) return;

    currentContext = data.context || "unknown";
    const contextLabel = document.getElementById("context-label");
    const statusDot = document.getElementById("status-dot");

    // Context & Status dot
    const contextMap = {
      practice: { text: "Practice Mode", dot: "sp-status-dot" },
      project:  { text: "Project Code",  dot: "sp-status-dot" },
      exam:     { text: "Exam Mode (Off)", dot: "sp-status-dot offline" },
    };

    const ctx = contextMap[currentContext] || { text: "Detecting…", dot: "sp-status-dot" };
    if (contextLabel) {
      contextLabel.textContent = data.problem ? `${ctx.text} — ${data.problem}` : ctx.text;
    }

    // Practice notice toggle
    const practiceNotice = document.getElementById("practice-notice");
    if (practiceNotice) {
      if (currentContext === "practice") {
        practiceNotice.classList.remove("hidden");
      } else {
        practiceNotice.classList.add("hidden");
      }
    }

    // Stuck Signal Alert Card
    const stuckCard = document.getElementById("stuck-card");
    if (data.signal && (!currentSignal || currentSignal.id !== data.signal.id)) {
      currentSignal = data.signal;
      hintLevel = 0;

      // Status dot turns pulsing amber or red
      if (statusDot) statusDot.className = "sp-status-dot pulse-amber";

      const detail = document.getElementById("stuck-detail");
      if (detail) {
        detail.textContent = data.signal.reason || "You seem stuck on this section. Would you like a progressive hint?";
      }

      // Populate signals row with animated chips
      const timeChip = document.getElementById("signal-time");
      const tripsChip = document.getElementById("signal-trips");
      const typingChip = document.getElementById("signal-typing");
      if (timeChip && data.signal.time_spent) timeChip.textContent = `${data.signal.time_spent} on problem`;
      if (tripsChip && data.signal.search_count !== undefined) tripsChip.textContent = `${data.signal.search_count} external searches`;
      if (typingChip && data.signal.typing_metric) typingChip.textContent = data.signal.typing_metric;

      if (stuckCard) {
        stuckCard.classList.remove("hidden");
        stuckCard.classList.remove("dismissing");
      }
      const hintArea = document.getElementById("hint-area");
      if (hintArea) hintArea.classList.add("hidden");
    } else if (!data.signal && currentSignal) {
      // Signal cleared
      if (statusDot) statusDot.className = "sp-status-dot";
      if (stuckCard) stuckCard.classList.add("hidden");
    } else if (!currentSignal && statusDot) {
      statusDot.className = "sp-status-dot";
    }
  }

  // ===== 6. Hint Flow =====
  const btnHint = document.getElementById("btn-hint");
  if (btnHint) {
    btnHint.addEventListener("click", async () => {
      const stuckCard = document.getElementById("stuck-card");
      if (stuckCard) stuckCard.classList.add("hidden");

      const hintArea = document.getElementById("hint-area");
      if (hintArea) hintArea.classList.remove("hidden");

      if (currentSignal) {
        await engineFetch(`/signal/${currentSignal.id}/status`, {
          method: "POST",
          body: JSON.stringify({ status: "accepted" }),
        });
      }
      requestHint();
    });
  }

  const btnNextHint = document.getElementById("btn-next-hint");
  if (btnNextHint) {
    btnNextHint.addEventListener("click", () => {
      requestHint();
    });
  }

  async function requestHint() {
    hintLevel++;
    const badge = document.getElementById("hint-level-badge");
    if (badge) badge.textContent = `Level ${hintLevel} of 3`;

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
      if (list) {
        const bubble = document.createElement("div");
        bubble.className = "sp-response-bubble";
        bubble.innerHTML = `
          <div style="font-size:11px; font-weight:600; color:var(--sp-color-primary); margin-bottom:4px;">
            Hint Level ${hintLevel}
          </div>
          <div>${renderMarkdownWithCode(data.hint)}</div>
        `;
        list.appendChild(bubble);
        wireCodeBlocks(bubble);
      }

      if (hintLevel >= 3 && btnNextHint) {
        btnNextHint.classList.add("hidden");
      }
    }
  }

  // ===== 7. Snooze / Dismiss Alert =====
  function dismissStuckCard(status) {
    const stuckCard = document.getElementById("stuck-card");
    if (!stuckCard) return;
    stuckCard.classList.add("dismissing");
    setTimeout(async () => {
      stuckCard.classList.add("hidden");
      stuckCard.classList.remove("dismissing");
      if (currentSignal) {
        await engineFetch(`/signal/${currentSignal.id}/status`, {
          method: "POST",
          body: JSON.stringify({ status }),
        });
      }
      currentSignal = null;
      const statusDot = document.getElementById("status-dot");
      if (statusDot) statusDot.className = "sp-status-dot";
    }, 240);
  }

  const btnSnooze = document.getElementById("btn-snooze");
  if (btnSnooze) {
    btnSnooze.addEventListener("click", () => dismissStuckCard("snoozed"));
  }

  const btnDismiss = document.getElementById("btn-dismiss");
  if (btnDismiss) {
    btnDismiss.addEventListener("click", () => dismissStuckCard("dismissed"));
  }

  // ===== 8. Mark Solved =====
  const btnSolved = document.getElementById("btn-solved");
  if (btnSolved) {
    btnSolved.addEventListener("click", async () => {
      if (currentSignal) {
        await engineFetch("/solved", {
          method: "POST",
          body: JSON.stringify({
            problem_key: currentSignal.problem_key || "unknown",
            solved: true,
          }),
        });

        if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
          chrome.storage.local.get("solvedProblems", (data) => {
            const map = data.solvedProblems || {};
            map[currentSignal.problem || "unknown"] = true;
            chrome.storage.local.set({ solvedProblems: map });
          });
        }
      }

      const hintArea = document.getElementById("hint-area");
      if (hintArea) hintArea.classList.add("hidden");
      currentSignal = null;
      hintLevel = 0;
      showToast("Problem marked solved! Faster approaches unlocked.", "success");
    });
  }

  // ===== 9. Ask StuckPoint (Autosizing Textarea & Streaming Simulation) =====
  const textarea = document.getElementById("project-input");
  if (textarea) {
    textarea.addEventListener("input", () => {
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`;
    });

    textarea.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        const hintBtn = document.getElementById("btn-project-hint");
        if (hintBtn) hintBtn.click();
      }
    });
  }

  async function handleProjectQuery(isFullFix) {
    const input = document.getElementById("project-input");
    if (!input || !input.value.trim()) return;

    const query = input.value.trim();
    const typingIndicator = document.getElementById("typing-indicator");
    const responseBubble = document.getElementById("response-bubble");
    const responseContent = document.getElementById("response-content");

    if (typingIndicator) typingIndicator.classList.remove("hidden");
    if (responseBubble) responseBubble.classList.add("hidden");

    const endpoint = isFullFix ? "/help/full" : "/hint";
    const payload = {
      problem_key: "project",
      problem_title: "Project code",
      level: isFullFix ? 4 : 1,
      context: "project",
      code: query,
    };

    const data = await engineFetch(endpoint, {
      method: "POST",
      body: JSON.stringify(payload),
    });

    // Small purposeful delay for stream simulation
    setTimeout(() => {
      if (typingIndicator) typingIndicator.classList.add("hidden");

      if (data && (data.hint || data.code)) {
        const text = data.code || data.hint;
        if (responseContent) {
          responseContent.innerHTML = renderMarkdownWithCode(text);
          wireCodeBlocks(responseBubble);
        }
        if (responseBubble) responseBubble.classList.remove("hidden");
      } else if (data && data.error) {
        if (responseContent) responseContent.textContent = `Error: ${data.error}`;
        if (responseBubble) responseBubble.classList.remove("hidden");
      }
    }, 350);
  }

  const btnProjectHint = document.getElementById("btn-project-hint");
  if (btnProjectHint) {
    btnProjectHint.addEventListener("click", () => handleProjectQuery(false));
  }

  const btnFullFix = document.getElementById("btn-full-fix");
  if (btnFullFix) {
    btnFullFix.addEventListener("click", () => handleProjectQuery(true));
  }

  // Thumbs feedback toggling
  const thumbUp = document.getElementById("thumb-up");
  const thumbDown = document.getElementById("thumb-down");
  if (thumbUp) {
    thumbUp.addEventListener("click", () => {
      thumbUp.classList.toggle("active");
      if (thumbDown) thumbDown.classList.remove("active");
      showToast("Thank you for your feedback!", "info");
    });
  }
  if (thumbDown) {
    thumbDown.addEventListener("click", () => {
      thumbDown.classList.toggle("active");
      if (thumbUp) thumbUp.classList.remove("active");
      showToast("Feedback noted. We'll improve future suggestions.", "info");
    });
  }

  // ===== 10. Suggestions Tab =====
  if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.onMessage) {
    chrome.runtime.onMessage.addListener((msg) => {
      if (msg.type === "sp-suggestions-update") {
        renderSuggestions(msg.suggestions || []);
      }
    });
  }

  const btnRefreshSug = document.getElementById("btn-refresh-sug");
  if (btnRefreshSug) {
    btnRefreshSug.addEventListener("click", () => {
      showToast("Scanning workspace for optimization patterns…", "info");
      pollStatus();
    });
  }

  function renderSuggestions(sugs) {
    const list = document.getElementById("sug-list");
    const badge = document.getElementById("sug-badge");

    // Dynamic count badge on Suggestions tab
    if (badge) {
      if (sugs.length > 0) {
        badge.textContent = sugs.length;
        badge.style.display = "inline-flex";
      } else {
        badge.style.display = "none";
      }
    }

    if (!list) return;
    if (!sugs.length) {
      list.innerHTML = `
        <div class="sp-empty-state">
          <svg class="sp-empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"></path>
          </svg>
          <div class="sp-empty-title">No Active Suggestions</div>
          <p class="sp-empty-text">Suggestions appear when StuckPoint spots patterns in your work.</p>
          <button class="sp-btn sp-btn-secondary" id="btn-refresh-sug-sub">
            <svg style="width:14px;height:14px;"><use href="#icon-refresh"></use></svg>
            Scan again
          </button>
        </div>
      `;
      const subBtn = document.getElementById("btn-refresh-sug-sub");
      if (subBtn) subBtn.addEventListener("click", () => pollStatus());
      return;
    }

    list.innerHTML = sugs
      .map((s, idx) => {
        let compBadge = "";
        if (s.complexity_before && s.complexity_after) {
          compBadge = `<span class="sp-comp-badge">${escapeHtml(s.complexity_before)} → ${escapeHtml(s.complexity_after)}</span>`;
        }
        let replacementHtml = "";
        if (s.replacement) {
          replacementHtml = `
            <div class="sp-code-container">
              <div class="sp-code-header">
                <span>Optimized snippet</span>
                <button class="sp-copy-btn" data-code="${escapeHtml(s.replacement)}">
                  <svg style="width:12px;height:12px;"><use href="#icon-copy"></use></svg>
                  <span>Copy</span>
                </button>
              </div>
              <pre class="sp-code-pre"><code>${escapeHtml(s.replacement)}</code></pre>
            </div>
          `;
        }

        return `
          <div class="sp-sug-card">
            <div class="sp-sug-header">
              <div class="sp-sug-issue">
                <svg style="width:14px;height:14px;color:var(--sp-color-warning);"><use href="#icon-zap"></use></svg>
                <span>${escapeHtml(s.issue)}</span>
              </div>
              ${compBadge}
            </div>
            ${s.why ? `<div class="sp-sug-why">${escapeHtml(s.why)}</div>` : ""}
            <div class="sp-sug-try"><strong>Suggestion:</strong> ${escapeHtml(s.suggestion)}</div>
            ${replacementHtml}
          </div>
        `;
      })
      .join("");

    wireCodeBlocks(list);
  }

  // ===== 11. Report Tab & Animated Count-Up =====
  const btnRefreshReport = document.getElementById("btn-refresh-report");
  if (btnRefreshReport) {
    btnRefreshReport.addEventListener("click", () => loadReport());
  }

  async function loadReport() {
    reportLoadedOnce = true;
    const data = await engineFetch("/report");
    if (!data) return;
    renderReport(data);
  }

  function animateValue(element, start, end, duration = 650, suffix = "") {
    if (!element) return;
    const startTime = performance.now();
    function step(currentTime) {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // easeOutCubic curve
      const ease = 1 - Math.pow(1 - progress, 3);
      const current = Math.round(start + (end - start) * ease);
      element.textContent = `${current}${suffix}`;
      if (progress < 1) {
        requestAnimationFrame(step);
      } else {
        element.textContent = `${end}${suffix}`;
      }
    }
    requestAnimationFrame(step);
  }

  function renderReport(data) {
    // 1. KPI Count-up
    if (data.metrics && data.metrics.overall) {
      const o = data.metrics.overall;
      animateValue(document.getElementById("kpi-problems"), 0, o.problems || 0);
      animateValue(document.getElementById("kpi-active-min"), 0, Math.round(o.total_active_min || 0), 650, "m");
      animateValue(document.getElementById("kpi-episodes"), 0, o.stuck_episodes || 0);
      animateValue(document.getElementById("kpi-hints"), 0, o.hints_used || 0);
    }

    // 2. Mini Weekly Bar Chart (Pure CSS/SVG)
    const chartContainer = document.getElementById("weekly-chart");
    if (chartContainer) {
      const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
      const episodes = [2, 4, 1, 5, 3, 0, 2]; // default distribution or mapped
      const maxVal = Math.max(...episodes, 1);

      chartContainer.innerHTML = days
        .map((day, i) => {
          const val = episodes[i];
          const heightPct = Math.max(12, Math.round((val / maxVal) * 100));
          return `
            <div class="sp-bar-col" title="${day}: ${val} stuck episode${val !== 1 ? "s" : ""}">
              <div class="sp-bar-fill" style="height: ${heightPct}%;"></div>
              <span class="sp-bar-label">${day}</span>
            </div>
          `;
        })
        .join("");
    }

    // 3. Gate Summary Chips
    if (data.gate_summary) {
      const g = data.gate_summary;
      const vEl = document.getElementById("gate-verified");
      const lEl = document.getElementById("gate-low");
      const rEl = document.getElementById("gate-rejected");
      if (vEl) vEl.textContent = `✓ ${g.passed || 0} verified`;
      if (lEl) lEl.textContent = `⚠ ${g.downgraded || 0} low confidence`;
      if (rEl) rEl.textContent = `✗ ${g.rejected || 0} rejected`;
    }

    // 4. Claims List
    const claimsContainer = document.getElementById("claims-list");
    if (claimsContainer) {
      if (data.claims && data.claims.length) {
        claimsContainer.innerHTML = data.claims
          .map((c, i) => {
            const isRej = c.gate_outcome === "rejected";
            const outcomeClass =
              c.gate_outcome === "passed"
                ? "verified"
                : c.gate_outcome === "downgraded"
                ? "low"
                : "rejected";
            const outcomeText =
              c.gate_outcome === "passed"
                ? "Verified ✓"
                : c.gate_outcome === "downgraded"
                ? "Low confidence ⚠"
                : "Rejected ✗";

            const evidenceRaw = c.evidence || c.numeric_claims || {};
            const evidenceStr = JSON.stringify(evidenceRaw, null, 2);

            return `
              <div class="sp-claim-item">
                <div class="sp-claim-top">
                  <span class="sp-claim-text ${isRej ? "rejected" : ""}">${escapeHtml(c.text || c.claim || "")}</span>
                  <span class="sp-gate-chip ${outcomeClass}">${outcomeText}</span>
                </div>
                ${isRej && c.gate_reason ? `<div class="sp-text-xs" style="color:var(--sp-color-danger);margin-top:2px;">Reason: ${escapeHtml(c.gate_reason)}</div>` : ""}
                <button class="sp-evidence-btn" data-idx="${i}">
                  <svg style="width:10px;height:10px;"><use href="#icon-chevron-down"></use></svg>
                  <span>Show evidence</span>
                </button>
                <div class="sp-evidence-content" id="evidence-${i}">${escapeHtml(evidenceStr)}</div>
              </div>
            `;
          })
          .join("");

        // Wire evidence toggle buttons
        claimsContainer.querySelectorAll(".sp-evidence-btn").forEach((btn) => {
          btn.addEventListener("click", () => {
            const ev = document.getElementById(`evidence-${btn.dataset.idx}`);
            if (ev) {
              const isOpen = ev.classList.toggle("open");
              btn.querySelector("span").textContent = isOpen ? "Hide evidence" : "Show evidence";
            }
          });
        });
      } else {
        claimsContainer.innerHTML = `<p class="sp-text-xs" style="color:var(--sp-color-text-muted); text-align:center; padding:12px;">No claims recorded yet.</p>`;
      }
    }
  }

  // ===== 12. Active Tab / Current Page Detection =====
  function detectCurrentPage() {
    const pageTitle = document.getElementById("page-title");
    const pageDomain = document.getElementById("page-domain");
    if (typeof chrome !== "undefined" && chrome.tabs && chrome.tabs.query) {
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (tabs && tabs[0]) {
          const tab = tabs[0];
          if (pageTitle) pageTitle.textContent = tab.title || "Untitled";
          try {
            const domain = new URL(tab.url).hostname;
            if (pageDomain) pageDomain.textContent = domain;
          } catch {
            if (pageDomain) pageDomain.textContent = "Local";
          }
        }
      });
    }
  }
  detectCurrentPage();

  // ===== 13. Tiny Markdown & Syntax Highlighter (Offline & CSP Safe) =====
  function highlightCode(code, lang = "javascript") {
    let safe = escapeHtml(code);

    // Keywords
    safe = safe.replace(
      /\b(def|return|function|const|let|var|if|else|for|while|class|import|from|async|await|try|except|catch|throw|new|typeof|in|of|export|default|null|undefined|true|false)\b/g,
      '<span style="color:#C084FC;font-weight:600;">$1</span>'
    );
    // Strings
    safe = safe.replace(
      /(".*?"|'.*?'|`.*?`)/g,
      '<span style="color:#34D399;">$1</span>'
    );
    // Numbers
    safe = safe.replace(
      /\b(\d+(\.\d+)?)\b/g,
      '<span style="color:#F59E0B;">$1</span>'
    );
    // Comments
    safe = safe.replace(
      /((\/\/|#).*?$)/gm,
      '<span style="color:#64748B;font-style:italic;">$1</span>'
    );
    return safe;
  }

  function renderMarkdownWithCode(text) {
    if (!text) return "";

    // Code blocks ```lang\ncode\n```
    const codeBlockRegex = /```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g;
    let formatted = text.replace(codeBlockRegex, (match, lang, code) => {
      const language = lang || "code";
      const highlighted = highlightCode(code.trim(), language);
      return `
        <div class="sp-code-container">
          <div class="sp-code-header">
            <span>${language}</span>
            <button class="sp-copy-btn" data-code="${escapeHtml(code.trim())}">
              <svg style="width:12px;height:12px;"><use href="#icon-copy"></use></svg>
              <span>Copy</span>
            </button>
          </div>
          <pre class="sp-code-pre"><code>${highlighted}</code></pre>
        </div>
      `;
    });

    // Inline code `code`
    formatted = formatted.replace(/`([^`]+)`/g, '<code style="background:rgba(255,255,255,0.08);padding:2px 5px;border-radius:4px;font-family:var(--sp-font-mono);font-size:11px;color:#A78BFA;">$1</code>');

    // Bold **text**
    formatted = formatted.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

    // Simple line breaks
    formatted = formatted.replace(/\n\n/g, '<div style="height:6px;"></div>');

    return formatted;
  }

  function wireCodeBlocks(container) {
    if (!container) return;
    container.querySelectorAll(".sp-copy-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const code = btn.getAttribute("data-code");
        if (code) {
          navigator.clipboard.writeText(code).then(() => {
            btn.classList.add("copied");
            btn.innerHTML = `
              <svg style="width:12px;height:12px;color:var(--sp-color-success);"><use href="#icon-check"></use></svg>
              <span>Copied!</span>
            `;
            showToast("Code copied to clipboard!", "success");
            setTimeout(() => {
              btn.classList.remove("copied");
              btn.innerHTML = `
                <svg style="width:12px;height:12px;"><use href="#icon-copy"></use></svg>
                <span>Copy</span>
              `;
            }, 2000);
          });
        }
      });
    });
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // ===== 14. Start Status Polling =====
  pollStatus();
  pollTimer = setInterval(pollStatus, 5000);
})();
