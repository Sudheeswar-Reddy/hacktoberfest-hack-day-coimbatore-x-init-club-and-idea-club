(() => {
  const SOURCE = "stuckpoint-page-bridge";
  let decorations = null;

  function findEditor() {
    return window.monaco?.editor?.getEditors?.()?.[0] || null;
  }

  function readEditor() {
    const editor = findEditor();
    if (editor) {
      return {
        code: editor.getValue(),
        language: editor.getModel?.()?.getLanguageId?.() || "text",
        monaco: true
      };
    }
    const lines = Array.from(document.querySelectorAll(".view-line"));
    return {code: lines.map((line) => line.textContent || "").join("\n"), language: "text", monaco: false};
  }

  function clearDecorations(editor) {
    if (!editor || !decorations) return;
    try {
      if (typeof decorations.clear === "function") decorations.clear();
      else editor.deltaDecorations(decorations, []);
    } catch {}
    decorations = null;
  }

  function markdownFor(suggestion) {
    const before = suggestion.complexity_before || "?";
    const after = suggestion.complexity_after || "?";
    const parts = [`**⚡ Faster approach** · ${before} → ${after}`, "", suggestion.issue || "Code improvement", "", suggestion.why || "", "", `*Try:* ${suggestion.suggestion || "Review this section."}`];
    if (suggestion.replacement) parts.push("", "```", String(suggestion.replacement).replace(/```/g, "ʼʼʼ"), "```");
    return parts.join("\n");
  }

  function applyDecorations(suggestions) {
    const editor = findEditor();
    if (!editor) return false;
    clearDecorations(editor);
    const monaco = window.monaco;
    const specs = (suggestions || []).filter((item) => Number.isInteger(item.start_line) && Number.isInteger(item.end_line) && item.start_line > 0 && item.end_line >= item.start_line)
      .map((item) => ({
        range: new monaco.Range(item.start_line, 1, item.end_line, 1),
        options: {
          isWholeLine: true,
          className: "sp-highlight",
          glyphMarginClassName: "sp-glyph",
          hoverMessage: {value: markdownFor(item), isTrusted: false, supportHtml: false}
        }
      }));
    if (!specs.length) return true;
    if (editor.createDecorationsCollection) {
      decorations = editor.createDecorationsCollection(specs);
    } else {
      decorations = editor.deltaDecorations([], specs);
    }
    return true;
  }

  window.addEventListener("message", (event) => {
    if (event.source !== window || event.data?.source !== "stuckpoint-extension") return;
    if (event.data.type === "READ_EDITOR") {
      const result = readEditor();
      window.postMessage({source: SOURCE, type: "EDITOR_CONTENT", requestId: event.data.requestId, ...result}, "*");
    } else if (event.data.type === "APPLY_SUGGESTIONS") {
      const ok = applyDecorations(event.data.suggestions || []);
      window.postMessage({source: SOURCE, type: "DECORATIONS_APPLIED", requestId: event.data.requestId, ok}, "*");
    } else if (event.data.type === "CLEAR_SUGGESTIONS") {
      clearDecorations(findEditor());
    }
  });
})();
