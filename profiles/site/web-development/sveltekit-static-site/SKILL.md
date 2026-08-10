---
name: sveltekit-static-site
description: SvelteKit SSG sites, prerender, entries, lean bundles.
---

# SvelteKit static-site work

For SvelteKit + Cloudflare Pages (SSG) codebases where the whole site is
`prerender = true` (set in the root `+layout.ts`). These patterns are durable
across this class of site.

## Verify commands (this repo)
`npm run check` (svelte-kit sync + svelte-check), `npm run lint`
(prettier + eslint), `npm run test:run` (vitest), `npm run build`,
`npm run build:<variant>` for the second variant. Run all of them before
claiming done; a build success is the only real proof a route prerendered.

## Prerendering a dynamic route with `[param]`
A fully-static site cannot serve arbitrary `[param]` URLs — they must be
enumerated at build time. In the route's `+page.server.ts`:

```ts
export const prerender = true;

/** One entry per valid param value. Anything not listed is simply not in the
 *  build and 404s on the host — that is how "404 on unknown X" is achieved
 *  for a static site. */
export const entries = async () => (await getAllThings()).map((t) => ({ param: t.slug }));

export const load = async ({ params }) => {
	const items = await getByThing(params.param);
	if (items.length === 0) throw error(404, `No such thing "${params.param}".`);
	return { /* data */ };
};
```

- `entries` may be `async` and may read dynamic data. It compiles the full set
  of prerender paths. SvelteKit does NOT require the dynamic route to also be
  reachable by link-crawling when `entries` is present, so this is the robust
  choice (other routes on the site rely on the link crawler instead).
- Because the route is prerendered, the `load` never hits the 404 branch for a
  listed entry; the 404 guards hand-written/bench-tested URLs at runtime only.
- TIP: for a heading on a slug-driven page, derive the display form from the
  data (e.g. the first matching item's original casing) rather than rendering
  the raw slug ("secure-boot" → "Secure Boot").

## Keep the client bundle lean: extract leaf modules
A pure helper shared by a server helper AND a client-rendered `.svelte` page
must NOT be imported from a module that pulls heavy build-time globs. In this
project `getPosts.ts` uses `import.meta.glob('/src/routes/posts/*.md')`; a
component importing a small util from it would drag every post's raw markdown
into the client bundle. Fix: put the pure function (`slugifyTag`) in its own
leaf module (`src/lib/tags.ts`) and import it from both the server helper and
the component. No new deps, DRY, tree-shakable.

## Named default export
`export default async () => {...}` creates no in-scope name, so sibling
functions in the same module cannot call the loader. Convert to
`export default async function getPosts() {...}` to reference it internally.
Note: converting the brace style via a `patch` can mangle closing braces /
indentation — if the diff looks bent, re-read the whole file and rewrite the
tail cleanly (or `write_file` the full file) rather than stacking more patches.

## Case-insensitive slug lookup
Normalize once on both sides and compare (lowercase, fold whitespace to
hyphens): slugify stored tag and slugify the incoming param, then compare
equality. Handles "NixOS" vs "nixos" and "Secure Boot" vs "secure-boot" on one
canonical page. Keep the canonical slug lowercase in URLs/sitemap; the lookup
merely tolerates case variation.

## Verifying prerendered output
After `npm run build`, the static pages live under
`.svelte-kit/cloudflare/` (mirrored in `.svelte-kit/output/prerendered/pages/`).
Grep the emitted HTML to confirm a route really rendered —
`find .svelte-kit/cloudflare/posts -name '*.html'` then grep `<title>` / `<h3>`.
Svelte scoped-styles hash class names (`class="chip svelte-xxxx"`), so grep for
the URL/href or strip tags rather than matching exact class strings.
`resolve()` emits relative hrefs (`../posts/tag/linux`) in prerendered output —
that is normal and resolves correctly.

## Sitemap & RSS for dynamic routes
If a route is part of the pub site, add it to the sitemap `+server.ts` render
function (e.g. append `/posts/tag/<slug>` for every tag after the posts block).
See `references/seanbehan-ca.md` for the two-variant (PUBLIC_SITE) specifics.

## Security headers & CSP on SvelteKit + Cloudflare Pages
Adding a strict CSP to a fully-prerendered SvelteKit site has traps:

- **`_headers` belongs at the PROJECT ROOT, not `static/`.** `@sveltejs/adapter-cloudflare`
  THROWS if `static/_headers` exists ("should be placed in the project root"),
  copies a root `_headers` into the output, then APPENDS an auto-generated block
  that gives `/_app/immutable/*` `Cache-Control: public, immutable, max-age=31536000`
  (via a `! Cache-Control` delete) and `/_app/*` `X-Robots-Tag: noindex` + no-cache.
  So hashed-asset immutable caching is free; you only add security headers and
  HTML revalidation (`pubic, max-age=0, must-revalidate`) yourself.
- **An inline `_headers` CSP cannot work here.** The built HTML ships an inline
  SvelteKit bootstrap script (`__sveltekit_<hash>`), and its hash/nonce is
  per-build, so a static header can't whitelist it. Instead set `kit.csp`
  (`mode: 'auto'`) in svelte.config.js: prerendered pages get the policy as a
  `<meta http-equiv=content-security-policy>` with `script-src ... 'sha256-...'`,
  and worker-served responses (see below) get a nonce-based CSP header. Let
  SvelteKit own the CSP; keep `_headers` to non-CSP headers only.
- **`style-src` needs `'unsafe-inline'`.** shiki token highlighting (and any
  `style="--enter-delay:..."` attributes) are inline style ATTRIBUTES; SvelteKit's
  CSP only hashes `<style>`/`<script>` it injects, never style attributes, so say
  `'self' 'unsafe-inline'`. `frame-ancestors`/`sandbox` are dropped from a meta-tag
  CSP (can't travel in meta) → do clickjacking with `X-Frame-Options: DENY` instead.
- **Two serving paths = two header sources.** adapter-cloudflare's `_routes.json`
  uses `include: ["/*"]` and, with many routes, hits Cloudflare's exclude-rule
  limit ("Dropping N exclude rules"); truncated excludes route much of the site
  (and every 404/unknown URL) through the Worker. Static-served pages get headers
  from `_headers`; worker-served responses get them from the `handle` hook in
  `src/hooks.server.ts`. Put the non-CSP security headers in BOTH (keep in sync),
  and add them in hooks only when `!dev` (dev keeps its no-store Cache-Control).
  External subresources to allow: an `<object data="https://...r2.dev/pdf">` needs
  `object-src` to name that origin; no forms/iframes → `form-action 'none'`,
  `frame-src 'none'`, `default-src 'self'`.
- **Preserve per-route `Cache-Control` in hooks**: set it only when the response
  has none, so a route handler's own value (e.g. the RSS feed's `max-age=3600`)
  survives the worker path. Check `response.headers.has('Cache-Control')` before
  setting your default.
- **Feed caching carve-out in `_headers`**: Cloudflare Pages CONCATENATES a
  header's value across every matching rule (it does not override), so a blanket
  `/* Cache-Control` silently clobbers `/rss.xml`'s intent. Override with the
  `! Header` delete + re-set pattern: `/rss.xml` → `! Cache-Control` then
  `Cache-Control: public, max-age=3600`. This is the same `!` trick the adapter's
  own autogenerated immutable block uses. NB `wrangler pages dev` may mis-emulate
  this (concatenates instead of `!`-replacing); trust the docs + the adapter's
  precedent over the local emulator.
- **HSTS**: Cloudflare Pages does NOT add it; ship
  `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`.
- **Test the CSP against real output**: add a `// @vitest-environment node` test
  that reads `.svelte-kit/cloudflare/*.html` (build-if-missing via `execSync`)
  and asserts the `content-security-policy` meta exists and `script-src` contains
  `'sha256-…'` but NOT `'unsafe-inline'` — catches a future analytics snippet that
  papers over inline scripts. This needs `@types/node` (devDep; tsconfig
  `skipLibCheck: true` keeps it from clashing with `@cloudflare/workers-types`,
  and explicit `node:*` imports resolve regardless of the `types` pin).

## Verifying CSP against the real build
`npm run build`, then `npx wrangler pages dev .svelte-kit/cloudflare --port 8788`
in background — wrangler applies `_headers` and runs `_worker.js`, so it exercises
BOTH the static and worker paths (a plain `vite preview`/static server would not
hit the worker path). `curl -sI` the HTML for `cache-control`/security headers and
an `/_app/immutable/entry/start.*.js` for immutable caching. In a real browser,
check the console for zero "Refused to ..." violations and prove ENFORCEMENT by
injecting `document.body.append(Object.assign(document.createElement('script'),
{textContent:'window.__pwned=1'}))` → `__pwned` must stay undefined, and
`try{eval('1')}catch{}` must throw.

