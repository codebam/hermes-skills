#!/usr/bin/env node
// Screenshot a URL through CDP with an emulated prefers-color-scheme.
//
//   node cdp-scheme-shot.mjs <url> <light|dark> <out.png> [WxH]
//
// Why: theme-dependent rendering (an adaptive favicon, any SVG loaded as an image, a
// page's dark styling) is not covered by the repo's gate, and a vision model returns
// prose, not a measurement. This renders the real thing in a real Chromium and hands
// back a PNG you can pixel-count.
//
// Needs Node >= 22 (global fetch + WebSocket) and a `chromium` on PATH (probe with
// `command -v chromium`, override with CHROMIUM=/path). No Playwright/puppeteer
// install is involved -- it drives the browser straight over the DevTools protocol.
//
// Gotchas baked in:
//   * an SVG *image* resolves its own media queries against the BROWSER scheme, not
//     the embedding page's CSS -- so emulate here, do not try to force it from HTML;
//   * file:// pages load file:// images fine, so the preview page needs no HTTP
//     server (and the terminal tool refuses foreground long-lived servers anyway);
//   * check the printed page scheme/background before trusting the shot -- if the
//     page's own @media chrome colours did not change, the emulation never applied.
import { spawn } from "node:child_process";
import fs from "node:fs";

const [url, scheme, out, size = "620x320"] = process.argv.slice(2);
if (!url || !["light", "dark"].includes(scheme) || !out) {
  console.error("usage: cdp-scheme-shot.mjs <url> <light|dark> <out.png> [WxH]");
  process.exit(2);
}
const chromeBin = process.env.CHROMIUM ?? "chromium";
const port = 9300 + Math.floor(Math.random() * 400);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const chrome = spawn(chromeBin, [
  "--headless", `--remote-debugging-port=${port}`, "--no-sandbox", "--disable-gpu",
  "--hide-scrollbars", "--no-first-run", "--no-default-browser-check",
  `--user-data-dir=/tmp/cdp-profile-${port}`, `--window-size=${size}`, "about:blank",
], { stdio: "ignore" });

async function pageWs() {
  for (let i = 0; i < 80; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      const page = list.find((t) => t.type === "page");
      if (page?.webSocketDebuggerUrl) return page.webSocketDebuggerUrl;
    } catch {}
    await sleep(250);
  }
  throw new Error("devtools endpoint never came up");
}

const ws = new WebSocket(await pageWs());
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let id = 0;
const pending = new Map();
const events = [];
ws.onmessage = (m) => {
  const msg = JSON.parse(m.data);
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
  else if (msg.method) events.push(msg.method);
};
function send(method, params = {}) {
  const mid = ++id;
  ws.send(JSON.stringify({ id: mid, method, params }));
  return new Promise((res, rej) =>
    pending.set(mid, (m) => (m.error ? rej(new Error(method + ": " + JSON.stringify(m.error))) : res(m.result))),
  );
}

await send("Page.enable");
await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: scheme }] });
await send("Page.navigate", { url });
for (let i = 0; i < 60 && !events.includes("Page.loadEventFired"); i++) await sleep(100);
await sleep(800); // let the SVG/image paint settle
const { data } = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
fs.writeFileSync(out, Buffer.from(data, "base64"));
const probe = await send("Runtime.evaluate", {
  expression: `JSON.stringify({pageScheme: matchMedia('(prefers-color-scheme: dark)').matches ? 'dark':'light', bodyBg: getComputedStyle(document.body).backgroundColor})`,
  returnByValue: true,
});
console.log(out, "->", probe.result.value, `(${fs.statSync(out).size} bytes)`);
ws.close();
chrome.kill();
process.exit(0);
