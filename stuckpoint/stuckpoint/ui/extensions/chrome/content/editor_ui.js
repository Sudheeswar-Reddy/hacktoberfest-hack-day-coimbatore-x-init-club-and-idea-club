(() => {
  const SOURCE = "stuckpoint-page-bridge";
  let requestNumber = 0;
  let pendingRead = null;
  let debounceTimer = null;
  let lastSuggestions = [];
  let fallbackCard = null;

  const button = document.createElement("button");
  button.type = "button";
  button.className = "sp-review-button";
  button.textContent = "⚡ Review my code";
  button.setAttribute("aria-label", "Review code with StuckPoint");
  document.documentElement.appendChild(button);

  function requestEditor() {
    return new Promise((resolve) => {
      const requestId = `read-${++requestNumber}`;
      const timeout = setTimeout(() => {
        if (pendingRead?.requestId === requestId) pendingRead = null;
        resolve(null);
      }, 1500);
      pendingRead = {requestId, resolve, timeout};
      window.postMessage({source: "stuckpoint-extension", type: "READ_EDITOR", requestId}, "*");
    });
  }

  function sendToEngine(path, method, body) {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({type: "STUCKPOINT_ENGINE_REQUEST", path, method, body}, (response) => {
        if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
        if (!response?.ok) return reject(new Error(response?.error || "Engine request failed"));
        resolve(response.data);
      });
    });
  }

  async function getContext() {
    let mode = "practice";
    let problemTitle = document.title.replace(/\s*-\s*LeetCode\s*$/i, "").trim();
    let problemKey = `leetcode:${location.pathname.split("/").filter(Boolean).at(-1) || "unknown"}`;
    try {
      const status = await sendToEngine("/status", "GET");
      if (status.context?.mode) mode = status.context.mode;
      if (status.context?.problem_title) problemTitle = status.context.problem_title;
      if (status.context?.problem_key) problemKey = status.context.problem_key;
    } catch {}
    const key = `stuckpoint.solved:${problemKey}`;
    const saved = await chrome.storage.local.get(key);
    return {mode, problemTitle, problemKey, solved: saved[key] === true};
  }

  function showFallback(suggestions) {
    document.querySelectorAll(".sp-line-highlight").forEach((node) => node.classList.remove("sp-line-highlight"));
    const lines = Array.from(document.querySelectorAll(".view-line"));
    for (const suggestion of suggestions) {
      for (let index = suggestion.start_line - 1; index < suggestion.end_line; index += 1) {
        if (lines[index]) lines[index].classList.add("sp-line-highlight");
      }
    }
    lastSuggestions = suggestions;
  }

  function renderFallbackCard(suggestion, x, y) {
    fallbackCard?.remove();
    const card = document.createElement("div");
    card.className = "sp-hover-card";
    const heading = document.createElement("strong");
    heading.textContent = `⚡ Faster approach · ${suggestion.complexity_before || "?"} → ${suggestion.complexity_after || "?"}`;
    const issue = document.createElement("p");
    issue.textContent = suggestion.issue || "Code improvement";
    const why = document.createElement("p");
    why.textContent = suggestion.why || "";
    const tryText = document.createElement("p");
    tryText.textContent = `Try: ${suggestion.suggestion || "Review this section."}`;
    card.append(heading, issue, why, tryText);
    if (suggestion.replacement) {
      const code = document.createElement("pre");
      code.textContent = suggestion.replacement;
      card.appendChild(code);
    }
    card.style.left = `${Math.min(x + 12, window.innerWidth - 440)}px`;
    card.style.top = `${Math.min(y + 12, window.innerHeight - 220)}px`;
    document.body.appendChild(card);
    fallbackCard = card;
  }

  function decorateFallback(suggestions) {
    showFallback(suggestions);
    const lines = Array.from(document.querySelectorAll(".view-line"));
    for (const suggestion of suggestions) {
      const line = lines[suggestion.start_line - 1];
      if (!line || line.dataset.spHoverBound) continue;
      line.dataset.spHoverBound = "1";
      line.addEventListener("mouseenter", (event) => renderFallbackCard(suggestion, event.clientX, event.clientY));
      line.addEventListener("mouseleave", () => { fallbackCard?.remove(); fallbackCard = null; });
    }
  }

  async function reviewCode() {
    button.disabled = true;
    button.textContent = "Reviewing…";
    try {
      const editor = await requestEditor();
      if (!editor?.code?.trim()) throw new Error("Could not read the editor. Try again after the problem editor loads.");
      const context = await getContext();
      const result = await sendToEngine("/suggest", "POST", {
        code: editor.code,
        language: editor.language || "text",
        problem_title: context.problemTitle,
        mode: context.mode,
        solved: context.solved
      });
      const suggestions = Array.isArray(result.suggestions) ? result.suggestions : [];
      const safeSuggestions = suggestions.map((item) => {
        if (context.mode === "practice" && !context.solved) return {...item, replacement: null};
        return item;
      });
      lastSuggestions = safeSuggestions;
      const requestId = `decor-${++requestNumber}`;
      window.postMessage({source: "stuckpoint-extension", type: "APPLY_SUGGESTIONS", requestId, suggestions: safeSuggestions}, "*");
      if (!editor.monaco) decorateFallback(safeSuggestions);
      button.textContent = safeSuggestions.length ? `⚡ ${safeSuggestions.length} suggestion${safeSuggestions.length === 1 ? "" : "s"}` : "No suggestions found";
    } catch (error) {
      button.textContent = error.message === "Failed to fetch" ? "Engine offline" : error.message;
      button.title = "Start StuckPoint engine at http://127.0.0.1:8765 and try again.";
    } finally {
      button.disabled = false;
      setTimeout(() => {
        if (button.isConnected && button.textContent !== "⚡ Review my code") {
          button.textContent = "⚡ Review my code";
        }
      }, 5000);
    }
  }

  button.addEventListener("click", () => { void reviewCode(); });

  window.addEventListener("message", (event) => {
    if (event.source !== window || event.data?.source !== SOURCE) return;
    if (event.data.type === "EDITOR_CONTENT" && pendingRead?.requestId === event.data.requestId) {
      clearTimeout(pendingRead.timeout);
      const resolve = pendingRead.resolve;
      pendingRead = null;
      resolve(event.data);
    }
  });

  // Debounce only on keystrokes; no key values are read or retained.
  document.addEventListener("keydown", () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => { void reviewCode(); }, 2000);
  }, true);
})();
