#!/bin/bash
# Launch a windowed Chromium against a URL with a requested colour scheme, report which
# favicon URLs it fetches, then capture the tab strip (browser chrome is not in headless shots).
#
# Usage: tabstrip-probe.sh <light|dark> <label> <url>
#   e.g. tabstrip-probe.sh dark inbox-dark "http://localhost:5173/"
# Needs: Xvfb on :99, scrot, imagemagick, python3 (for pixelmap.py), node (DOM probe).
set -u
SCHEME="${1:-dark}"; LABEL="${2:-probe}"; URL="${3:-about:blank}"
DISPLAY_NUM="${DISPLAY_NUM:-:99}"
PORT=$((9400 + RANDOM % 400))
PROFILE="/tmp/prof-$LABEL"
SHOT="/tmp/shot-$LABEL.png"
NETLOG="/tmp/net-$LABEL.json"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export HOME=/tmp

rm -rf "$PROFILE"; rm -f "$SHOT" "$NETLOG"

FLAGS=(--no-sandbox --disable-gpu --no-first-run --no-default-browser-check
       --window-size=1080,620 --window-position=0,0 --hide-scrollbars
       --remote-debugging-port="$PORT" --user-data-dir="$PROFILE" --log-net-log="$NETLOG")
[ "$SCHEME" = "dark" ] && FLAGS+=(--force-dark-mode)

DISPLAY=$DISPLAY_NUM chromium "${FLAGS[@]}" "$URL" >"/tmp/chrome-$LABEL.log" 2>&1 &
PID=$!
sleep 9   # favicon fetches land after load

# DOM facts through CDP (Node >= 22 has a global WebSocket).
node - "$PORT" <<'JS'
const port = process.argv[2];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  let page;
  for (let i = 0; i < 40 && !page; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      page = list.find((t) => t.type === 'page' && t.url.startsWith('http'));
    } catch {}
    if (!page) await sleep(250);
  }
  if (!page) return console.log('  dom: no page target');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  ws.send(JSON.stringify({ id: 1, method: 'Runtime.evaluate', params: {
    expression: `JSON.stringify({scheme: matchMedia('(prefers-color-scheme: dark)').matches ? 'dark':'light',
      links: Array.from(document.querySelectorAll('link[rel="icon"]')).map(l => ({type: l.type, href: l.getAttribute('href')}))})`,
    returnByValue: true } }));
  const out = await new Promise((res) => { ws.onmessage = (m) => res(JSON.parse(m.data)); });
  console.log('  dom: ' + (out.result && out.result.result && out.result.result.value));
  ws.close(); process.exit(0);
})();
JS

DISPLAY=$DISPLAY_NUM scrot -o "$SHOT"
kill $PID 2>/dev/null; sleep 1; kill -9 $PID 2>/dev/null

echo "--- $LABEL ($SCHEME) ---"
echo "  favicon fetches:"; grep -o '"url":"[^"]*favicon[^"]*"' "$NETLOG" 2>/dev/null | sed 's/.*\/\///' | sort | uniq -c | sed 's/^/    /'
echo "  screenshot: $SHOT"
if command -v python3 >/dev/null && [ -f "$SCRIPT_DIR/pixelmap.py" ]; then
  python3 "$SCRIPT_DIR/pixelmap.py" "$SHOT" 44 6 46 24 "$LABEL tab icon"
fi
