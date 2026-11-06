// Regenerates the README screenshots in docs/screenshots from the demo server.
// Usage: start the demo (`make demo`), then `node scripts/screenshots.mjs [base-url]`.
// Drives headless Chrome over the DevTools protocol so it can emulate a real phone viewport.
import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const BASE = process.argv[2] ?? "http://localhost:8000";
const OUT = new URL("../docs/screenshots/", import.meta.url);
const CHROME = process.env.CHROME ?? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = 9333;

const SHOTS = [
  { file: "dashboard-light.png", path: "/", width: 1440, height: 1500, scheme: "light" },
  { file: "dashboard-dark.png", path: "/", width: 1440, height: 1500, scheme: "dark" },
  { file: "holding-startup.png", path: "/assets/8", width: 1440, height: 1250, scheme: "light" },
  { file: "holding-etf.png", path: "/assets/1", width: 1440, height: 1250, scheme: "light" },
  { file: "mobile-dark.png", path: "/", width: 390, height: 1500, scheme: "dark", mobile: true },
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const chrome = spawn(CHROME, [
  "--headless=new", "--disable-gpu", "--hide-scrollbars", `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${mkdtempSync(join(tmpdir(), "po-shots-"))}`, "about:blank",
], { stdio: "ignore" });

try {
  let target;
  for (let i = 0; i < 50 && !target; i++) {
    await sleep(200);
    try {
      target = (await (await fetch(`http://127.0.0.1:${PORT}/json`)).json()).find((t) => t.type === "page");
    } catch { /* Chrome not up yet */ }
  }
  if (!target) throw new Error("Chrome did not start");

  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener("open", r));
  let id = 0;
  const pending = new Map();
  ws.addEventListener("message", (e) => {
    const m = JSON.parse(e.data);
    pending.get(m.id)?.(m);
    pending.delete(m.id);
  });
  const send = (method, params = {}) =>
    new Promise((r) => {
      const n = ++id;
      pending.set(n, r);
      ws.send(JSON.stringify({ id: n, method, params }));
    });

  await send("Page.enable");
  for (const s of SHOTS) {
    await send("Emulation.setDeviceMetricsOverride", { width: s.width, height: s.height, deviceScaleFactor: 2, mobile: !!s.mobile });
    await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: s.scheme }] });
    await send("Page.navigate", { url: BASE + s.path });
    await sleep(3500); // let data load and charts measure their width
    const shot = await send("Page.captureScreenshot", { format: "png" });
    writeFileSync(new URL(s.file, OUT), Buffer.from(shot.result.data, "base64"));
    console.log("wrote docs/screenshots/" + s.file);
  }
  ws.close();
} finally {
  chrome.kill();
}
