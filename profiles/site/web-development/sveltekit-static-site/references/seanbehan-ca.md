# seanbehan.ca — two-variant SvelteKit site (Cloudflare Pages)

Real writable checkout: `/home/codebam/Documents/git/seanbehan.ca` (the
`/var/lib/hermes/workspace/...` path is a read-only mirror — use the git copy).

## Two site variants
One repo, one set of posts, two Cloudflare Pages projects. The variant is
chosen at build time by the `PUBLIC_SITE` env var (`seanbehan` | `codebam`),
inlined by Vite as `__SITE_ID__`. See `src/lib/site.ts`:

- `npm run build` → default (seanbehan.ca)
- `npm run build:codebam` → `PUBLIC_SITE=codebam vite build` (codebam.ca)

Everything that differs between variants lives in `src/lib/site.ts`
(`site.name`, `site.url`, `site.email`, `site.showResume`, ...). New pages
should read name/title/url from `site` (e.g. `<title>{x} — {site.name}</title>`,
sitemap via `absolute(path)` from `src/lib/site.ts`) so both variants stay
correct; the site's own posts-index page hardcodes "Sean Behan", which is a
latent variant inconsistency — don't copy that pattern into new pages.

## Layout / conventions
- Whole site is `prerender = true` (root `src/routes/+layout.ts`). Since it is
  SSG, dynamic routes use `entries`-based prerendering and unknown params 404
  because they are simply not in the build.
- Posts are markdown in `src/routes/posts/*.md` (mdsvex). `getPosts.ts` loads
  them via `import.meta.glob('/src/routes/posts/*.md')` and returns newest-first.
- Tag feature (reference implementation from the tag-browsing work):
  - `src/lib/tags.ts` — leaf module with `slugifyTag()` (lowercase, ws→hyphen).
  - `src/lib/getPosts.ts` — `getAllTags()` (TagInfo[]: tag/slug/count,
    most-tagged first) and `getPostsByTag(slug)` (case-insensitive, newest first).
  - `src/routes/posts/tag/[tag]/+page.server.ts` exports `entries` enumerating
    every tag slug; page reuses `<PostList>`.
  - `src/routes/posts/tags/+page.svelte` — tag index (pill chips with counts).
  - Post page renders `meta.tags` as links to `/posts/tag/<slug>`.
- Styling uses CSS tokens from `src/app.css` (`var(--line)`, `var(--accent)`,
  `var(--muted)`, `var(--text)`) plus Tailwind; scoped `<style>` blocks in
  components. No extra deps.

## Verify
`npm run check` (svelte-kit sync + svelte-check), `npm run lint`
(prettier + eslint), `npm run test:run` (vitest), `npm run build`,
`npm run build:codebam`. Confirm prerendered output under
`.svelte-kit/cloudflare/posts/tag/*.html` and in sitemap
`<loc>https://<domain>/posts/tag/<slug></loc>`.
