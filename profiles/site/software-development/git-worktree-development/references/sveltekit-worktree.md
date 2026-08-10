# SvelteKit worktree verification recipe

Captured from the seanbehan.ca "add reading time in a worktree" task. Reuse the
verification loop whenever a feature lands in a fresh worktree of a SvelteKit /
mdsvex / Cloudflare project.

## Setup

```bash
git worktree add -b <branch> /path/to/<repo>-<feature> master
cd /path/to/<repo>-<feature>
ln -s /path/to/main/repo/node_modules node_modules
```

Do NOT symlink `.svelte-kit` — it is regenerated and carries per-worktree
generated route types.

## Fresh-worktree gotcha: LSP noise before sync

A new worktree has no `.svelte-kit`, so `$lib` aliases do not resolve yet and
the editor/TS reports "Cannot find module '$lib/...'" on EVERY import,
including ones that existed before your change. This is expected and not a
real error. Run `npx svelte-kit sync` (or `npm run check`) and the diagnostics
clear.

## Verify

```bash
npx svelte-kit sync
npm run check      # 0 errors / 0 warnings expected
npm run test:run   # vitest
npm run lint       # prettier --check + eslint
npm run build      # vite build -> Cloudflare adapter
```

## Confirm it actually rendered

Compiling is not rendering. For a prerendered site, the built HTML lives under
`.svelte-kit/output/prerendered/pages/`. Grep for the shipped output:

```bash
grep -o '[0-9]* min read' \
  .svelte-kit/output/prerendered/pages/posts/<slug>.html
```

Spot-check one short post (expect a min value like "1 min read") and one long
post (expect a non-trivial value like "3 min read") to confirm the
word-counting logic actually scales.
