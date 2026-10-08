const ENGINE = "http://127.0.0.1:8765";
const QUEUE_KEY = "stuckpoint.eventQueue";
const LAST_SIGNAL_KEY = "stuckpoint.lastNotifiedSignal";
const MAX_QUEUED_EVENTS = 500;
let flushing = false;

async function readQueue() {
  const saved = await chrome.storage.session.get(QUEUE_KEY);
  return Array.isArray(saved[QUEUE_KEY]) ? saved[QUEUE_KEY].map((item) =>
    item?.queueId && item?.payload ? item : {queueId: crypto.randomUUID(), payload: item}
  ) : [];
}

async function queueEvents(events) {
  const queue = await readQueue();
  queue.push(...events.map((event) => ({queueId: crypto.randomUUID(), payload: event})));
  if (queue.length > MAX_QUEUED_EVENTS) queue.splice(0, queue.length - MAX_QUEUED_EVENTS);
  await chrome.storage.session.set({[QUEUE_KEY]: queue});
}

async function flushEvents() {
  if (flushing) return;
  const queue = await readQueue();
  if (!queue.length) return;
  flushing = true;
  try {
    const batch = queue.slice(0, MAX_QUEUED_EVENTS);
    const response = await fetch(`${ENGINE}/events`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({source: "chrome", events: batch.map((item) => item.payload)})
    });
    if (!response.ok) throw new Error(`engine returned ${response.status}`);
    const sentIds = new Set(batch.map((item) => item.queueId));
    const latestQueue = await readQueue();
    await chrome.storage.session.set({[QUEUE_KEY]: latestQueue.filter((item) => !sentIds.has(item.queueId))});
  } catch (error) {
    console.debug("StuckPoint event delivery deferred:", error.message);
  } finally {
    flushing = false;
  }
}

async function requestEngine(path, method = "GET", body) {
  if (!path.startsWith("/")) throw new Error("Engine paths must be relative.");
  const response = await fetch(`${ENGINE}${path}`, {
    method,
    headers: {"Content-Type": "application/json"},
    ...(body === undefined ? {} : {body: JSON.stringify(body)})
  });
  const text = await response.text();
  let data = {};
  try { data = text ? JSON.parse(text) : {}; } catch { data = {detail: text}; }
  if (!response.ok) throw new Error(data.detail || `Engine returned ${response.status}`);
  return data;
}

async function pollStatus() {
  try {
    const result = await requestEngine("/status");
    const signal = result.signal;
    if (!signal || signal.status !== "confirmed" || !signal.id) return;
    const saved = await chrome.storage.local.get(LAST_SIGNAL_KEY);
    if (saved[LAST_SIGNAL_KEY] === signal.id) return;
    await chrome.storage.local.set({[LAST_SIGNAL_KEY]: signal.id});
    await chrome.notifications.create(signal.id, {
      type: "basic",
      iconUrl: chrome.runtime.getURL("icons/icon128.png"),
      title: "StuckPoint",
      message: `Stuck on ${signal.problem_title || "this problem"}? Click for a hint.`
    });
  } catch (error) {
    // The extension remains usable while the local engine is stopped.
    console.debug("StuckPoint engine is not available:", error.message);
  }
}

async function openPanelForSignal(signalId) {
  try {
    await requestEngine(`/signal/${encodeURIComponent(signalId)}/status`, "POST", {status: "offered"});
  } catch (error) {
    console.debug("Could not update signal status:", error.message);
  }
  try {
    const [tab] = await chrome.tabs.query({active: true, lastFocusedWindow: true});
    if (tab?.windowId !== undefined) await chrome.sidePanel.open({windowId: tab.windowId});
  } catch (error) {
    console.debug("Could not open StuckPoint side panel:", error.message);
  }
}

chrome.runtime.onInstalled.addListener(async () => {
  await chrome.sidePanel.setPanelBehavior({openPanelOnActionClick: true});
  await chrome.alarms.create("stuckpoint-poll", {periodInMinutes: 0.5});
});

chrome.runtime.onStartup.addListener(async () => {
  await chrome.sidePanel.setPanelBehavior({openPanelOnActionClick: true});
  await chrome.alarms.create("stuckpoint-poll", {periodInMinutes: 0.5});
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "stuckpoint-poll") {
    void flushEvents();
    void pollStatus();
  }
});

chrome.notifications.onClicked.addListener((notificationId) => {
  void openPanelForSignal(notificationId);
  chrome.notifications.clear(notificationId);
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "STUCKPOINT_TRACK_EVENT") {
    void queueEvents([message.event]).then(() => flushEvents())
      .then(() => sendResponse({ok: true}))
      .catch((error) => sendResponse({ok: false, error: error.message}));
    return true;
  }
  if (message?.type === "STUCKPOINT_ENGINE_REQUEST") {
    void requestEngine(message.path, message.method || "GET", message.body)
      .then((data) => sendResponse({ok: true, data}))
      .catch((error) => sendResponse({ok: false, error: error.message}));
    return true;
  }
  if (message?.type === "STUCKPOINT_OPEN_PANEL") {
    void openPanelForSignal(message.signalId).then(() => sendResponse({ok: true}));
    return true;
  }
  return false;
});

// Best effort while the worker is awake; the alarm is the service-worker-safe backup.
setInterval(() => { void flushEvents(); }, 10_000);
