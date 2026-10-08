// editor_ui.js — isolated world (LeetCode pages)
// Debounces typing, requests suggestions from the engine via background, builds hover cards
(function () {
  let debounceTimer = null;
  let bridgeReady = false;
  let currentSuggestions = [];

  // Listen for bridge responses
  window.addEventListener("message", (e) => {
    if (!e.data || e.data.source !== "stuckpoint-bridge") return;

    if (e.data.action === "ready") {
      bridgeReady = true;
    }

    if (e.data.action === "code-result") {
      if (e.data.code) {
        requestSuggestions(e.data.code, e.data.language);
      }
    }
  });

  // Request code from bridge after typing pause
  function requestCode() {
    if (bridgeReady) {
      window.postMessage({ source: "stuckpoint", action: "get-code" }, "*");
    }
  }

  // Debounce: request code 2s after last keydown
  document.addEventListener("keydown", () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(requestCode, 2000);
  }, true);

  // Send code to engine for suggestions
  function requestSuggestions(code, language) {
    // Get status first (for mode + solved)
    chrome.runtime.sendMessage({ type: "sp-get-status" }, (status) => {
      const mode = status?.context || "practice";
      if (mode === "exam" || mode === "other") return;

      chrome.storage.local.get("solvedProblems", (data) => {
        const problemTitle = document.title.replace(" - LeetCode", "").trim();
        const solvedMap = data.solvedProblems || {};
        const solved = !!solvedMap[problemTitle];

        chrome.runtime.sendMessage(
          {
            type: "sp-suggest",
            payload: { code, language, problem_title: problemTitle, mode, solved },
          },
          (response) => {
            const sugs = response?.suggestions || [];
            currentSuggestions = sugs;
            applySuggestions(sugs, mode, solved);
          }
        );
      });
    });
  }

  // Build markdown for each suggestion card
  function buildMarkdown(s, mode, solved) {
    let md = `**⚡ Faster approach**`;
    if (s.complexity_before && s.complexity_after) {
      md += ` · ${s.complexity_before} → ${s.complexity_after}`;
    }
    md += `\n\n${s.issue}\n\n*${s.why}*\n\n**Try:** ${s.suggestion}`;

    if (mode === "practice" && !solved) {
      md += `\n\n---\n_Mark the problem solved in StuckPoint to see the faster code._`;
    } else if (s.replacement) {
      md += `\n\n\`\`\`${s.language || ""}\n${s.replacement}\n\`\`\``;
    }
    return md;
  }

  // Apply suggestions as decorations (via bridge) or DOM fallback
  function applySuggestions(sugs, mode, solved) {
    if (sugs.length === 0) return;

    const withMarkdown = sugs.map((s) => ({
      ...s,
      markdown: buildMarkdown(s, mode, solved),
    }));

    // Try Monaco decorations via bridge
    if (bridgeReady) {
      window.postMessage(
        { source: "stuckpoint", action: "apply-decorations", suggestions: withMarkdown },
        "*"
      );
    } else {
      // DOM fallback — highlight .view-line elements
      applyDOMFallback(withMarkdown);
    }
  }

  // Fallback: highlight view-lines + show hover card
  function applyDOMFallback(sugs) {
    // Remove old highlights
    document.querySelectorAll(".sp-dom-highlight").forEach((el) => el.remove());
    document.querySelectorAll(".sp-hover-card").forEach((el) => el.remove());

    const viewLines = document.querySelectorAll(".view-line");
    if (!viewLines.length) return;

    sugs.forEach((s) => {
      for (let i = s.start_line - 1; i < Math.min(s.end_line, viewLines.length); i++) {
        const line = viewLines[i];
        if (!line) continue;
        const rect = line.getBoundingClientRect();
        const overlay = document.createElement("div");
        overlay.className = "sp-dom-highlight";
        overlay.style.cssText = `
          position: absolute; left: ${rect.left + window.scrollX}px;
          top: ${rect.top + window.scrollY}px; width: ${rect.width}px;
          height: ${rect.height}px; pointer-events: auto; z-index: 9998;
        `;

        // Hover card
        overlay.addEventListener("mouseenter", () => {
          showHoverCard(s, overlay);
        });
        overlay.addEventListener("mouseleave", () => {
          setTimeout(() => {
            const card = document.querySelector(".sp-hover-card");
            if (card && !card.matches(":hover")) card.remove();
          }, 200);
        });

        document.body.appendChild(overlay);
      }
    });
  }

  function showHoverCard(s, anchor) {
    document.querySelectorAll(".sp-hover-card").forEach((el) => el.remove());

    const card = document.createElement("div");
    card.className = "sp-hover-card";

    let html = `<div class="sp-card-title">⚡ Faster approach`;
    if (s.complexity_before && s.complexity_after) {
      html += ` <span class="sp-card-complexity">${s.complexity_before} → ${s.complexity_after}</span>`;
    }
    html += `</div>`;
    html += `<div class="sp-card-issue">${s.issue}</div>`;
    html += `<div class="sp-card-why">${s.why}</div>`;
    html += `<div class="sp-card-suggestion"><strong>Try:</strong> ${s.suggestion}</div>`;

    if (s.replacement) {
      html += `<pre class="sp-card-code">${s.replacement}</pre>`;
    }

    card.innerHTML = html;

    const rect = anchor.getBoundingClientRect();
    card.style.top = `${rect.bottom + window.scrollY + 4}px`;
    card.style.left = `${rect.left + window.scrollX}px`;

    card.addEventListener("mouseleave", () => card.remove());
    document.body.appendChild(card);
  }
})();
