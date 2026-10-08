(() => {
  if (location.protocol === "chrome:" || location.protocol === "chrome-extension:" ||
      location.protocol === "edge:" || location.protocol === "about:") return;

  let keys = 0;
  let clicks = 0;

  document.addEventListener("keydown", () => { keys += 1; }, true);
  document.addEventListener("click", () => { clicks += 1; }, true);

  function send(event) {
    try {
      chrome.runtime.sendMessage({type: "STUCKPOINT_TRACK_EVENT", event});
    } catch {
      // The service worker may be restarting; counters are sent again next interval.
    }
  }

  setInterval(() => {
    const focused = document.visibilityState === "visible" && document.hasFocus();
    if (focused) {
      send({
        type: "focus",
        ts: new Date().toISOString(),
        app: "Google Chrome",
        title: document.title,
        url: location.href
      });
      // Zero counts are meaningful: they let the engine measure low-input periods.
      send({type: "input", ts: new Date().toISOString(), app: "Google Chrome", keys, clicks});
      keys = 0;
      clicks = 0;
    } else if (keys || clicks) {
      send({type: "input", ts: new Date().toISOString(), app: "Google Chrome", keys, clicks});
      keys = 0;
      clicks = 0;
    }
  }, 10_000);
})();
