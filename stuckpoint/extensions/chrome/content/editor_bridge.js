// editor_bridge.js — MAIN world (can access window.monaco)
// Reads Monaco editor code and applies decorations
(function () {
  let decorationCollection = null;

  function getEditor() {
    if (typeof monaco !== "undefined" && monaco.editor) {
      const editors = monaco.editor.getEditors ? monaco.editor.getEditors() : [];
      return editors[0] || null;
    }
    return null;
  }

  // Listen for requests from editor_ui.js (isolated world)
  window.addEventListener("message", (e) => {
    if (!e.data || e.data.source !== "stuckpoint") return;

    if (e.data.action === "get-code") {
      const ed = getEditor();
      if (ed) {
        const code = ed.getValue();
        const lang = ed.getModel()?.getLanguageId() || "unknown";
        window.postMessage({
          source: "stuckpoint-bridge",
          action: "code-result",
          code,
          language: lang,
        }, "*");
      } else {
        window.postMessage({
          source: "stuckpoint-bridge",
          action: "code-result",
          code: null,
          language: null,
        }, "*");
      }
    }

    if (e.data.action === "apply-decorations") {
      const ed = getEditor();
      if (!ed) return;

      // Clear old decorations
      if (decorationCollection) {
        decorationCollection.clear();
      }

      const sugs = e.data.suggestions || [];
      if (sugs.length === 0) return;

      decorationCollection = ed.createDecorationsCollection(
        sugs.map((s) => ({
          range: new monaco.Range(s.start_line, 1, s.end_line, 1),
          options: {
            isWholeLine: true,
            className: "sp-highlight",
            glyphMarginClassName: "sp-glyph",
            hoverMessage: { value: s.markdown },
          },
        }))
      );
    }
  });

  // Signal that the bridge is ready
  window.postMessage({ source: "stuckpoint-bridge", action: "ready" }, "*");
})();
