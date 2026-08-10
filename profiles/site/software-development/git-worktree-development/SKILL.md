---
name: git-worktree-development
description: Develop a feature in an isolated git worktree.
version: 1.0.0
license: MIT
author: hermes
platforms: [linux]
metadata:
  hermes:
    tags: [git, worktree, workflow, sveltekit, node]
---

# Developing in a git worktree

## When to Use
Use when the user says "do it in a worktree", or when feature work must stay
off the main branch: create a fresh worktree rather than editing the main
checkout or reusing another in-progress worktree.

## Steps

```bash
# From the real repo checkout:
git worktree add -b <feature-branch> <path-to-worktree> master
```

Pick the new worktree path near the repo, e.g. `<repo>-reading-time`, and a
branch name with no collisions. `git worktree list` shows existing worktrees —
if a stale leftover worktree already exists for the same topic (common after
interrupted sessions, e.g. under `/tmp/`), DO NOT reuse it: create a fresh one
off `master` unless the user says otherwise.

### Share node_modules instead of reinstalling

A fresh worktree has no `node_modules` and reinstalling a large JS project is
slow. Symlink it from the main checkout:

```bash
cd <worktree>
ln -s /path/to/main/repo/node_modules node_modules
```

This works because node resolves the symlink. `.svelte-kit` is regenerated per
worktree by `svelte-kit sync` (see below) — don't symlink that one.

## Verify inside the worktree (SvelteKit example)

A fresh worktree has no generated `.svelte-kit`, so TypeScript/LSP diagnostics
will falsely report "Cannot find module '$lib/...'" until sync. Run sync first:

```bash
npx svelte-kit sync
npm run check      # svelte-kit sync + svelte-check
npm run test:run
npm run lint
npm run build
```

Confirm the change actually rendered, not just that it compiles — for a
prerendered SvelteKit site, grep the built pages:

```bash
grep -o '[0-9]* min read' .svelte-kit/output/prerendered/pages/posts/<slug>.html
```

See `references/sveltekit-worktree.md` for the full recipe.

## Pitfalls

- **Read-only home / optimistic `safe.directory`**: on hosts with an immutable
  home (NixOS) the repo may be owned by another user and `~/.config/git/config`
  may be read-only, so `git config --global --add safe.directory ...` fails
  ("Read-only file system") and `--local` fails outside a repo. Inject config
  per-session with environment variables instead (worktree-safe, no file
  writes):
  ```bash
  export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=/path/to/repo
  ```
  Exported env persists across terminal calls in the same session.
- **Co-located test import paths**: a test file living in the same directory as
  the module under test must import it with `./module`, not `../module` — `..`
  resolves one level above the test's own directory. Vitest fails with a
  confusing "Failed to resolve import" if you get this wrong.
- **Don't commit unless asked**: leave changes uncommitted in the worktree and
  report the branch/path; the user decides when to commit and merge.
