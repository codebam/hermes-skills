---
name: cloudflare-workers
description: Develop/debug Cloudflare Workers; verify UI in browser.
version: 1.0.0
author: hermes-curator
license: MIT
metadata:
  hermes:
    tags: [cloudflare, wrangler, hono, workers, r2, frontend]
    related_skills: [cloudflare-temporary-deploy]
---

# Cloudflare Workers (Hono) development

## When to Use

Use when building, debugging, or reviewing any Hono / `@cloudflare/workers`
project that runs under `wrangler dev` — especially ones with inlined HTML
templates, a UI to interact with (paste/submit/copy), or that serve multiple
domains from one worker. Triggers: a "fix doesn't take effect after build",
wrong absolute URL returned, or copy button that silently does nothing.

How to build, debug, and—critically—*verify* Hono-based Cloudflare Workers
before pushing. The user operates live workers on multiple domains and expects
UI/workflow fixes proven in a browser, not just a passing `tsc`.

## Verify in a real browser BEFORE pushing/deploying (mandatory)

Do NOT conclude a fix works from `tsc` / `npm run build` alone — a transpile
pass proves nothing about runtime behaviour. Reproduce the bug and prove the
fix against the actual served page:

- Reproduce on the **live site** first (inspect the served HTML/JS for the bug).
- Fix the source, then rebuild and re-serve via `npx wrangler dev --port <p>`.
- Drive a headless browser (browser_navigate/console/snapshot tools, or
  Playwright) to: type → submit → read the returned URL → click every copy
  button → assert the success notification / class change → measure layout
  (e.g. input.right vs button.left for overlap).
- Only after the in-browser check passes, commit and push.

This machine already runs `google-chrome` (user's live browser) and a headless
chromium with `--remote-debugging-port=9222` for automation — browser tooling
is available, so use it rather than guessing.

## Build-system trap: inline-import silently inlines STALE HTML

The common Hono worker setup inlines HTML as strings:

```ts
// @ts-expect-error inline import
import index_html from 'inline:./index.html';
```

esbuild's `inline-import` plugin resolves `./index.html` **relative to the
compiled entry file** (e.g. `dist/index.js`), so it reads `dist/index.html`,
NOT `src/index.html`. If `dist/` isn't regenerated with the current `src/`
HTML before esbuild runs, the deployed bundle keeps whatever stale HTML was
last copied there — changes to `src/*.html` appear to "not take effect".

Fix the build script to copy the HTML into the same dir esbuild reads from,
before both `tsc` and esbuild:

```json
"build": "mkdir -p dist && cp src/index.html src/highlight.html dist/ && tsc --project tsconfig.json; node esbuild.mjs"
```

`dist/` is usually gitignored; only `src/` is the source of truth.

## Multi-domain: build URLs dynamically from the request

If one worker serves several domains (e.g. `p.example.com` and `paste.example.com`)
and returns absolute URLs, the reply must match the domain THE CLIENT USED.

Two independent layers break this:

1. **Hardcoded frontend fetch** — the page JS calls `fetch('https://p.example.com')`
   unconditionally, so every paste URL comes back as that domain no matter which
   site you're on. Fix: POST/fetch same-origin (`fetch('/')`).
2. **Wrong origin on the server** — `new URL(c.req.url).origin` can be the wrong
   host/scheme behind Cloudflare. Construct the origin from the request headers
   the edge actually sets:

```ts
function getBaseUrl(c) {
  const proto = c.req.header('x-forwarded-proto') || new URL(c.req.url).protocol.replace(':', '');
  const host = c.req.header('host') || new URL(c.req.url).host;
  return `${proto}://${host}`;
}
```

Use it for every route that returns a URL (`POST /`, `POST /:id`, move, etc.).
Quick curl confidence check for the server layer:

```sh
curl -s -X POST -H "host: paste.example.com" -d hi http://localhost:<port>/   # -> http://paste.example.com/<id>
curl -s -X POST -H "host: p.example.com" -H "x-forwarded-proto: https" -d hi http://localhost:<port>/  # -> https://p.example.com/<id>
```

## Copy-button / clipboard pitfalls

- **Inline `onclick` needs a GLOBAL function.** `<button onclick="copyToClipboard()">`
  resolves against `window`. If `copyToClipboard` is declared inside a
  `document.addEventListener('DOMContentLoaded', function(){...})` closure, the
  handler throws `ReferenceError: copyToClipboard is not defined` — the classic
  "button does nothing" bug. Define inline-handler functions at global scope, or
  attach the listener via `addEventListener` inside the closure. Do not mix both.
- **`navigator.clipboard.writeText` fails** in real browsers when the tab is
  unfocused or permission is denied (`NotAllowedError`). Provide a fallback to a
  hidden textarea + `document.execCommand('copy')`, and prefer it when
  `!navigator.clipboard || !window.isSecureContext`. Wrap the fallback so `done()`
  always runs.

## wrangler dev caveats

- `wrangler dev` runs the `build.command` from `wrangler.toml` (`npm install &&
  npm run build`) on change, but it does not reliably rebuild HTML-only edits —
  after touching `src/*.html`, **restart** the dev server to be sure it serves
  the current code rather than assuming the watcher caught it.
- Start the dev server in the background and poll its log / `curl -o /dev/null -w
  "%{http_code}"` until you see `Ready on http://localhost:<port>` and a `200`.
- Built endpoint behaviour (URL domains, headers) is best checked with `curl`
  first; frontend interactivity (clicks, clipboard, layout) with a browser.

## References

- `references/pastebin-r2-debug.md` — full worked case: dual-domain pastebin,
  the stale-HTML cause, the inline-onclick ReferenceError, and the exact
  browser-verification sequence used.