// tracker.js — content script (all pages)
// Sends focus heartbeats + input counts every 10s
(function () {
  if (location.protocol === "chrome:" || location.protocol === "chrome-extension:") return;

  let keys = 0;
  let clicks = 0;

  document.addEventListener("keydown", () => { keys++; }, true);
  document.addEventListener("click", () => { clicks++; }, true);

  function sendEvents() {
    if (document.visibilityState !== "visible" || !document.hasFocus()) return;

    const ts = new Date().toISOString();
    const app = "Google Chrome";
    const title = document.title;
    const url = location.href;

    // Focus heartbeat
    chrome.runtime.sendMessage({
      type: "sp-event",
      event: { type: "focus", ts, app, title, url },
    });

    // Input counts
    if (keys > 0 || clicks > 0) {
      chrome.runtime.sendMessage({
        type: "sp-event",
        event: { type: "input", ts, app, keys, clicks },
      });
      keys = 0;
      clicks = 0;
    }
  }

  setInterval(sendEvents, 10000);
})();
