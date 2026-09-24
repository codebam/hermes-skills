# Theme-adaptive assets (favicon) — wiring, engine reality, verification

## What ships in this repo

- `public/favicon.svg` — adaptive default (dark glyph, media query switching to `#f5f5f5`),
  linked from `app/root.tsx` with `data-light="/favicon.svg" data-dark="/favicon-dark.svg"`.
- `public/favicon-dark.svg` — fixed light glyph for dark mode.
- `public/favicon.ico` (unchanged legacy fallback, dark artwork) and `public/favicon-dark.ico`
  (same envelope, rendered light), both 48/32/16.
- The only theme signal is the OS setting. `SYSTEM_THEME_SCRIPT` in `app/root.tsx` mirrors
  `prefers-color-scheme` onto `document.documentElement[data-mode]` (Kumo reads that) and
  re-points every `link[data-favicon]` href; the head also carries
  `<meta name="color-scheme" content="light dark">`. There is no in-app theme toggle.
- The script must stay AFTER the icon links in `<head>` (it runs at parse time), and the links
  carry `suppressHydrationWarning` because the script changes their `href` before hydration.

## Why per-scheme artwork is required (measured — do not relitigate)

- **Chromium picks the `.ico` and never fetches the SVG.** With the old markup the network log
  showed four requests to `/favicon.ico` and zero to `/favicon.svg`; the candidate that declares
  concrete `sizes` wins, whatever order the links are in. So an in-SVG media query reaches no
  user in Chrome.
- **A favicon SVG ignores its own media queries.** Forcing Chrome to fetch the SVG still rendered
  the light glyph on the dark tab strip, while the same file as an `<img>` in the page rendered
  `#f5f5f5`. Safari behaves the same by its own bug tracker.
- **`.ico` cannot adapt**, and browsers cache favicons per URL: separate file names are what make
  a fix visible (and what dodges a stale bitmap after an in-place edit).
- The media query stays inside `favicon.svg` anyway — it is correct for bookmarks/readers and for
  engines that render the file directly; it is just not the mechanism the tab icon uses.

## Generating the dark `.ico`

Render each frame at its own size instead of downscaling one large raster (crisper strokes on a
light-on-dark icon):

```bash
for s in 16 32 48; do
  chromium --headless --no-sandbox --disable-gpu --hide-scrollbars \
    --default-background-color=00000000 --window-size=$s,$s \
    --screenshot=/tmp/glyph-$s.png file:///tmp/favicon-dark.svg
done
magick /tmp/glyph-48.png /tmp/glyph-32.png /tmp/glyph-16.png public/favicon-dark.ico
```

Verify the result, not the command: parse the ICO directory (frames 48/32/16, DIB 32bpp) and
count pixels with `alpha >= 200` per frame — it should land within a few pixels of the light
icon's count (the envelope is ~210 opaque pixels at 32px), with the dominant fill `#F5F5F5`.

## Verify against the real thing

Browser-chrome verification (windowed Chromium under Xvfb, `--log-net-log`, luminance-band pixel
maps, hard-pixel magnification) is the `browser-chrome-assets` skill's territory —
`references/verifying-browser-rendering.md` plus its two scripts. What the last run of this
repo measured, as the expectation to reproduce:

- dark UI → fetches `/favicon-dark.ico`; tab glyph pixels are all BRIGHTER than the tab
  background (peak `#E0` on a `#3C` tab), none darker.
- light UI → fetches `/favicon.ico`; glyph pixels all darker than the white tab.
- `node scripts/cdp-scheme-shot.mjs` (headless, CDP-emulated scheme) is still useful for the
  file's own render and for page-level checks, but it is a proxy for the tab strip — say so if
  it is all you have.
- SSR head assertion: `curl http://localhost:5173/` while the dev server runs (see the SKILL.md
  bullet on running the app) and grep for `data-dark="/favicon-dark.(svg|ico)"`, with the script
  offset after both links.
- Ship check: `npm run build` then compare `public/favicon*` with `build/client/favicon*` — equal
  bytes prove all four assets copied.

## Gaps to state out loud

- Safari ignores media queries inside SVG images, and engines without SVG favicon support use the
  `.ico` — which is dark artwork in light mode by design. Do not claim the icon adapts "everywhere".
- A favicon fix on local `main` is invisible to the user until the app is deployed
  (`npm run deploy`); if he is looking at `email.codebam.ca`, say that instead of asking him to
  clear a cache.
