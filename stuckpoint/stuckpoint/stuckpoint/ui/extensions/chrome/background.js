// background.js — StuckPoint service worker
const ENGINE = "http://127.0.0.1:8765";
let eventBuffer = [];

// Open side panel on icon click
chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });

// Buffer events from content scripts and flush every 10s
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "sp-event") {
    eventBuffer.push(msg.event);
    sendResponse({ ok: true });
  }
  if (msg.type === "sp-get-status") {
    fetch(`${ENGINE}/status`)
      .then(r => r.json())
      .then(data => sendResponse(data))
      .catch(() => sendResponse({ context: "unknown", signal: null }));
    return true; // async
  }
  if (msg.type === "sp-suggest") {
    fetch(`${ENGINE}/suggest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(msg.payload),
    })
      .then(r => r.json())
      .then(data => sendResponse(data))
      .catch(() => sendResponse({ suggestions: [] }));
    return true;
  }
  if (msg.type === "sp-hint") {
    fetch(`${ENGINE}/hint`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(msg.payload),
    })
      .then(r => r.json())
      .then(data => sendResponse(data))
      .catch(() => sendResponse({ error: "Engine offline" }));
    return true;
  }
  if (msg.type === "sp-solved") {
    fetch(`${ENGINE}/solved`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(msg.payload),
    })
      .then(r => r.json())
      .then(data => sendResponse(data))
      .catch(() => sendResponse({ ok: false }));
    return true;
  }
  if (msg.type === "sp-report") {
    fetch(`${ENGINE}/report`)
      .then(r => r.json())
      .then(data => sendResponse(data))
      .catch(() => sendResponse({ error: "Engine offline" }));
    return true;
  }
});

// Flush buffered events to the engine
async function flushEvents() {
  if (eventBuffer.length === 0) return;
  const batch = eventBuffer.splice(0, 500);
  try {
    await fetch(`${ENGINE}/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: "chrome", events: batch }),
    });
  } catch {
    // Engine offline — put events back
    eventBuffer.unshift(...batch);
    if (eventBuffer.length > 500) eventBuffer = eventBuffer.slice(-500);
  }
}

// Flush every 10 seconds
setInterval(flushEvents, 10000);

// Alarm as MV3 keepalive (minimum 30s)
chrome.alarms.create("sp-poll", { periodInMinutes: 0.5 });

let lastSignalId = null;

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name !== "sp-poll") return;
  flushEvents();
  try {
    const res = await fetch(`${ENGINE}/status`);
    const data = await res.json();
    if (data.signal && data.signal.id !== lastSignalId) {
      lastSignalId = data.signal.id;
      chrome.notifications.create(data.signal.id, {
        type: "basic",
        iconUrl: "icons/icon128.png",
        title: "Stuck?",
        message: `Looks like you've been stuck on ${data.signal.problem || "this problem"}. Click for a hint.`,
      });
    }
  } catch { /* engine offline */ }
});

chrome.notifications.onClicked.addListener((notifId) => {
  chrome.sidePanel.open({ windowId: undefined });
  fetch(`${ENGINE}/signal/${notifId}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: "offered" }),
  }).catch(() => {});
});
