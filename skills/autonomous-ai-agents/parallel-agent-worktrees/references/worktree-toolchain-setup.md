# Worktree toolchain setup

Make a fresh worktree pass the repo's real gate BEFORE any child is dispatched (rule 5). A
setup that only half-works burns every child's budget, and its failures are silent: a symlink
that points nowhere, a generated file nobody copied, a package that resolves to the main
checkout instead of the worktree.

## Dependency tree

- Symlink the shared tree at the depth the worktree actually sits — for a worktree nested one
  level deeper than the repo root, `ln -sfn ../../../node_modules <worktree>/node_modules`.
  Verify with `readlink <worktree>/node_modules`: silent setup failures are the common case.
- A `.gitignore` entry of `node_modules/` (trailing slash) matches directories only, so the
  symlink shows as untracked in every worktree. A bare `node_modules` entry matches both;
  otherwise stage explicit paths and tell children to.
- Packages resolve by walking up the directory tree, so a worktree INSIDE the repo reaches the
  hoisted root tree even without a symlink — but `npx`/`tsc` also need `node_modules/.bin`,
  so create the symlink anyway and verify it.

## Generated artifacts to copy or regenerate per worktree

A fresh worktree checks out committed files only; anything gitignored but required by the
toolchain must be copied in or regenerated:

- Wrangler / Cloudflare: `worker-configuration.d.ts` — referenced from `tsconfig.json`
  (`include` or `types`); absent, `tsc` fails with file-not-found before reporting anything
  useful. `cp` it in; `wrangler types --check` then validates it.
- SvelteKit: `.svelte-kit/` (route types) and `node_modules/$app` — regenerate with
  `npx svelte-kit sync` run inside the worktree.
- Whatever else the repo's check command regenerates: make the check command itself the setup
  step, then assert it exits 0.

## The framework-generated-package trap

Some frameworks generate a package into the app's `node_modules` whose config carries RELATIVE
paths (SvelteKit's `$app/tsconfig` maps `$lib` to `../../src/lib` and sets `rootDirs`). If the
worktree's `node_modules` is a symlink to the main checkout's, that package resolves to the
MAIN app's files: the worktree's edits are never typechecked and the gate lies green.

Fix: give the worktree a real (empty) `node_modules` directory and run the generator
(`npx svelte-kit sync`) inside the worktree; other packages still resolve by walking up to the
hoisted tree. After a sync, confirm the main checkout's generated package is untouched (mtime
check) — a generator writing through a symlink mutates shared state.

## Probe-worktree recipe

```bash
# create + set up
mkdir -p <repo>/.worktrees  # or <sub>/.worktrees for a submodule
(cd <sub> && git worktree add .worktrees/probe -b probe-toolchain)
ln -sfn ../../../node_modules <sub>/.worktrees/probe/node_modules        # plain app
mkdir -p <sub>/.worktrees/probe/node_modules                            # framework-generated pkg
(cd <sub>/.worktrees/probe && npx svelte-kit sync)
cp <sub>/worker-configuration.d.ts <sub>/.worktrees/probe/
# run the SAME check a child will run, not a weaker one
(cd <sub>/.worktrees/probe && <repo's real check>)                      # must be green
# tear down
(cd <sub> && git worktree remove --force .worktrees/probe && git branch -D probe-toolchain)
```

Then repeat the setup for the real worktrees and verify each one: `readlink` on the symlink,
generated files present, `git status` clean.

## Per-flag probes without touching the committed config

To verify one compiler flag in a worktree without editing the committed `tsconfig.json` (which
N parallel branches would then conflict over):

- `tsc`: CLI flags override the tsconfig — `npx tsc --noEmit --<flag>`; boolean-off works too
  (`--allowUnreachableCode false`).
- `svelte-check`: no CLI flag overrides — write a throwaway `tsconfig.probe.json`
  (`{"extends": "./tsconfig.json", "compilerOptions": {"<flag>": true}}`), run
  `npx svelte-check --tsconfig ./tsconfig.probe.json`, parse the summary line (`found N errors`).
  Delete the probe before committing; it must never ride into a merge.

## Anchors and line numbers

Patch by exact content anchors, not by line number. When the working tree may have been
touched, verify the anchor against the committed file (`git show HEAD:<file>`), and when a
line-numbered file view disagrees with the compiler's reported position, trust the compiler —
inspect with `awk 'NR>=X && NR<=Y' <file>`.
