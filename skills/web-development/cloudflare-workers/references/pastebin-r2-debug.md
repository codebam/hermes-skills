# Worked case: pastebin-r2 — bugs hidden by "build passes"

Project: Hono Cloudflare Worker + R2 (Cloudflare pastebin), a git repo allowed
only `src/` (dist is gitignored). Served on two domains pointing at the same
worker: `p.seanbehan.ca` and `paste.codebam.ca`.

User reported (and confirmed still-broken live): pasting from
`paste.codebam.ca` returned a `https://p.seanbehan.ca/<id>` URL, and the copy
button did nothing. I had "fixed" the server twice via `tsc`/build, pushed, and
it stayed broken — exactly why source-level checks are insufficient.

## Diagnosis sequence that actually worked

1. Kill chase: `ps aux | grep -E "wrangler|workerd serve"` to learn what dev
   server / browser automation is already running (a wrangler dev was on
   :8787; a headless chromium was on --remote-debugging-port=9222).
2. Drive a browser at the LIVE site (`paste.codebam.ca`) and read the served
   inline <script> text:
   - `domainsReferenced` and a slice around `p.seanbehan.ca` showed
     `fetch('https://p.seanbehan.ca', {...})` hardcoded in the served JS —
     the frontend always POSTed to p.seanbehan.ca, so every URL came back as
     that domain. The server-side origin logic was never even reached for the
     wrong-domain case.
3. Submitting on the live site returned `https://p.seanbehan.ca/<id>` while
   sitting on `paste.codebam.ca` — reproduced the exact reported URL.
4. Testing the copy button: clicking "Copy to Clipboard" succeeded, but the
   URL-copy button produced no notification. `typeof copyToClipboard` +
   direct call threw `ReferenceError: copyToClipboard is not defined`. Cause:
   the function was declared inside the `document.addEventListener(
   'DOMContentLoaded', function(){ ... })` closure, yet the button wired it
   with inline `onclick="copyToClipboard()"` which resolves against `window`.

## Fixes (all verified in-browser before push)

- Frontend: `fetch('https://p.seanbehan.ca', ...)` → `fetch('/')` (same-origin)
  in both index.html and highlight.html.
- Server: moved origin building to a `getBaseUrl(c)` helper using
  `x-forwarded-proto` + `host` headers (see SKILL.md), applied to `POST /` and
  `POST /:id`.
- Copy buttons: defined the URL-copy handler (and its `execCommand` fallback)
  at GLOBAL scope so the inline `onclick` resolves; textarea copy buttons kept
  their closure `addEventListener` but routed both through one robust helper
  that falls back to `document.execCommand('copy')` when the Clipboard API is
  unavailable/blocked.
- Layout: copy URL box overlapped the button → `.url-display input { flex:
  1 1 auto; min-width:0; width:0; box-sizing:border-box }` and the button
  `flex:0 0 auto; white-space:nowrap`.
- Build: `package.json` build script now `mkdir -p dist && cp src/*.html dist/`
  before `tsc`/esbuild so the inlined HTML is always current.

## Browser-verification script used

- `curl` for the server layer: POST with varying `host:` / `x-forwarded-proto`
  headers, assert returned URL matches.
- browser_navigate → type text → click Submit → read `#paste-url` value and
  assert `startsWith(location.origin)`.
- Copy verification: click each copy button, then check the success class
  changed (`#notification.classList.contains('show')`) or `#notification-area`
  gained a child. Note Clipboard API resolves async — wait, or use a
  MutationObserver on the notification class.
- Layout: compare `input.getBoundingClientRect().right` to
  `button.getBoundingClientRect().left` (expect equal, no overlap) and button
  right ≤ container right.

## Gotchas seen

- `hljs is not defined` on the highlight view in an offline headless browser —
  highlight.js CDN failed to load. That is environment, not a code bug; the
  worker fetched the content fine.
- Restart wrangler dev after HTML edits — the watcher did not rebuild the
  HTML-only change; the freshly-started server on a new port (:8790) served
  the corrected page.
- Inline-import + minify: helper names are renamed in dist/index.mjs, so grep
  the bundle for surviving string literals (`x-forwarded-proto`,
  `execCommand`) rather than function names when confirming the deploy bundle.