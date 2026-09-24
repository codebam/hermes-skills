---
name: browser-chrome-assets
description: Use when a favicon is wrong in dark mode or won't update.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [favicon, browser-chrome, dark-mode, icons, verification, pixel-evidence]
    related_skills: [agentic-inbox, dogfood, parallel-agent-worktrees]
---

# Browser-chrome assets (favicons and friends)

Assets the browser draws OUTSIDE the page: the tab icon, pinned-tab icon, home-screen icon,
`theme-color`. They do not inherit page styling, no component test and no headless page
screenshot covers them, and browsers disagree about which declaration wins — so every claim
about them needs a measurement from a real browser, never from a proxy.

## When to Use

- Making a favicon (or any icon the browser draws outside the page) follow light/dark mode.
- A tab icon that is invisible, wrong, or unchanged after you edited the file.
- Verifying browser-chrome rendering: which asset the browser fetched, and what it drew.

## What is actually true (measured — do not relitigate)

- **With several `<link rel="icon">` candidates, the browser picks.** Chromium takes the one
  that declares concrete `sizes`: an `.ico` with `sizes="48x48 32x32 16x16"` wins and the SVG is
  **never requested at all**, however early it appears. Confirm with a request log
  (`--log-net-log`), never by reasoning about order or format.
- **A favicon SVG ignores the media queries inside it.** `@media (prefers-color-scheme: dark)` in
  `favicon.svg` has no effect on the tab strip (Safari by its own bug tracker; Chromium
  rasterises the favicon with the default scheme). The same file embedded as `<img>` or opened
  directly DOES adapt — which is exactly how a "verified" fix ships broken.
- **`.ico` cannot adapt.** If that is what the browser picked, both schemes show that artwork.
- **Favicons cache by URL**, separately from the page and aggressively: an edited file at the
  same URL often keeps showing the old bitmap, so new per-scheme file names are part of the fix.

## Procedure

1. Inventory the existing head links and assets, and find the theme signal the app already
   trusts (`data-mode`/`class="dark"` written by a pre-paint script, a framework provider, or
   plain `matchMedia`).
2. Ship per-scheme artwork for every format in play: an adaptive default (`favicon.svg`, media
   query kept for bookmark/reader contexts), a dark SVG, and an `.ico` pair (`favicon.ico` +
   `favicon-dark.ico`) for engines without SVG favicon support. Keep both links in the head.
3. Generate `.ico` frames at their native sizes (16/32/48) rather than downscaling one large
   raster, compose them (`magick f48.png f32.png f16.png out.ico`), then verify the file by
   parsing its directory and counting `alpha >= 200` pixels per frame against the light icon's
   count.
4. Wire the swap into the app's existing pre-paint theme script: each icon link carries
   `data-light`/`data-dark` and the script re-points `href` on change, so one signal drives both
   UI and icon. If the app has a manual toggle, drive it from that toggle's resolved mode.
5. Put the script AFTER the icon links in `<head>` — an inline head script runs at parse time
   and finds no links if it precedes them. Add `suppressHydrationWarning` to the links when SSR
   plus React hydration is in play.
6. Verify against the real thing (`references/verifying-browser-rendering.md`): read the network
   log for which favicon URL was fetched, and window-render the tab strip for both schemes.
   Then gate the repo normally.
7. Report the outcome with its gaps: what the browser fetched, what the tab drew, which engines
   were not verified, and whether the running deployment has the change yet (a favicon fix is
   invisible until the app is deployed).

## Pitfalls

- **A render is not a use.** An `<img>`/CDP screenshot of the asset, or opening the file
  directly, proves the FILE; only a request log proves the browser fetched it as the tab icon,
  and only a windowed browser shows what the tab draws. Verify the mechanism the product uses,
  not a proxy that happens to share the file.
- **Headless screenshots contain no browser chrome.** Install the missing pieces rather than
  skipping the check: `apt-get install -y xvfb scrot imagemagick`, then `Xvfb :99 -screen
  0 1100x700x24 &`. Only a windowed run shows the tab strip.
- **Exact-fill pixel counts lie at icon sizes.** A 16px glyph has almost no fully-opaque pixels,
  so `#f5f5f5 == 0` reads as "the fix failed" when it worked. Classify pixels into luminance
  bands and compare against the LOCAL background of the tab, not the whole image.
- **Do not ask a vision model to judge a blurred upscale.** Box-filtered magnification washes
  thin light strokes into "muddy grey"; magnify with hard pixels (`magick -filter point -resize
  800%`), and read the pixel map yourself before trusting any prose description.
- **Size/order folklore is not a rule.** "Add `sizes=any`", "list the SVG last" — outcomes
  differ per engine and version. Measure with the request log, then record what you measured in
  the commit message.
- **The user's "it doesn't work" outranks your earlier verification.** Reproduce in the real
  client before theorising, then fix; a cache-busting explanation is only credible after you
  have seen which URL the browser actually fetched.

## Support files

- `references/verifying-browser-rendering.md` — the install lines, flags and commands for
  request-log and windowed-tab-strip evidence, and how to read the pixels.
- `scripts/tabstrip-probe.sh` — launch a windowed Chromium against a URL with a requested colour
  scheme, dump the favicon fetches and icon-link hrefs, and grab the tab strip.
- `scripts/pixelmap.py` — print a screenshot region as a hex/luminance map with the local
  background identified.
