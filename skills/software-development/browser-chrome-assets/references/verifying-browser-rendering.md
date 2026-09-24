# Verifying browser-chrome rendering

Two questions need two different measurements: **which asset did the browser fetch** (request
log) and **what did the tab draw** (windowed screenshot + pixels). A headless page screenshot
answers neither.

## Install the pieces (minimal images usually lack them)

```bash
apt-get update && apt-get install -y xvfb scrot imagemagick
# ffmpeg in some images is built without x11grab, so capture with scrot, not ffmpeg.
Xvfb :99 -screen 0 1100x700x24 &      # long-lived: start it as a background process
```

## Which favicon URL was fetched

```bash
chromium --headless --no-sandbox --disable-gpu --user-data-dir=/tmp/prof-fresh \
  --log-net-log=/tmp/net.json "$URL" &
sleep 8; kill %1
grep -o '"url":"[^"]*favicon[^"]*"' /tmp/net.json | sort | uniq -c
```

- Fresh `--user-data-dir` per run: the favicon service caches per profile, so a reused profile
  answers with the previous fetch.
- `--force-dark-mode` puts Chromium's UI, and the scheme it reports to pages, in dark mode.
  Confirm it took effect by evaluating `matchMedia('(prefers-color-scheme: dark)').matches` in
  the page (CDP or a line of on-page JS) — a light run masquerading as dark invalidates the
  whole experiment.
- This is the cheapest check and often the whole diagnosis: an SVG link that never appears in
  the log was never a candidate.

## What the tab drew

`scripts/tabstrip-probe.sh <light|dark> <label> <url>` launches a windowed Chromium with the
requested scheme, prints the favicon fetches plus a DOM probe of the icon-link hrefs, and
captures the tab strip with `scrot`. Then read the pixels with
`scripts/pixelmap.py <shot.png> <x> <y> <w> <h> <label>`, or by hand:

```bash
magick shot.png -crop 20x17+50+9 +repage txt:- | head
magick shot.png -crop 240x28+0+4 +repage -filter point -resize 500% zoom.png
```

- Locate the icon from a coarse map of the whole strip first (the tab tile, the tab-search
  button and the title text all produce pixels); the favicon sits between the tab's left edge
  and the title.
- Compare against the LOCAL background: a light glyph on a dark tab is "pixels brighter than
  the background, none darker"; the inverted artwork shows the opposite with near-zero contrast.
- Keep the screenshots — a stacked light-row / dark-row image at hard-pixel magnification is the
  artifact a user can check in one look, and it is the only claim worth making.

## DOM facts without dependencies

Node's global `WebSocket` (Node >= 22) drives CDP with no packages: fetch
`http://127.0.0.1:<devtools-port>/json/list`, connect to the page target, then
`Runtime.evaluate` with e.g.

```js
JSON.stringify({
  scheme: matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light',
  links: Array.from(document.querySelectorAll('link[data-favicon]')).map(l => l.getAttribute('href')),
})
```

That proves the swap script ran and which file each link now points at — the piece a screenshot
cannot show when the icon is tiny.

## What this cannot prove

Non-Chromium engines (state them as gaps), other platforms, and anything behind a login you do
not have. Say which part of the matrix was measured and which was reasoned about.
