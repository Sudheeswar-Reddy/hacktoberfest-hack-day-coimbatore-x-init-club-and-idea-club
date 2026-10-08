const engineStatus = document.getElementById("engine");

async function checkEngine() {
  try {
    const response = await fetch("http://127.0.0.1:8765/health");
    if (!response.ok) throw new Error();
    const health = await response.json();
    engineStatus.textContent = `Engine online · ${health.model || "StuckPoint"}`;
  } catch {
    engineStatus.textContent = "Engine offline · start StuckPoint on port 8765";
  }
}

void checkEngine();
setInterval(checkEngine, 5000);
