---
name: parallel-agent-worktrees
description: Use when delegating features to parallel worktree agents.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [multi-agent, git-worktree, delegation, parallel-implementation, merge-gate]
    related_skills: [merge-reconciler, plan, requesting-code-review]
---

# Parallel Agent Worktrees

Implement a batch of independent changes by giving each one its own `git worktree` and its
own subagent, then merging the branches behind the repo's verification gate. This is for
batch work ("implement all of these", "do these five features"), not for a single small
change you would just make yourself.

## Non-negotiables

1. **Worktrees live inside the workspace, never beside it.** A sandboxed or bind-mounted
   workspace does not expose sibling directories: `git worktree add ../wt-x` creates a path
   the agents then cannot see or build in. Use `<repo>/.worktrees/<name>` and add
   `.worktrees/` to `.gitignore` before creating any.
2. **Symlink the dependency tree, never install per worktree.**
   `ln -sfn ../../node_modules .worktrees/<n>/node_modules` keeps one shared `node_modules`
   serving every branch. Ban `npm install` in every brief — one child installing into the
   shared symlink corrupts every sibling mid-run.
3. **Copy gitignored generated files into each worktree.** A fresh worktree checks out
   committed files only, so generated artifacts (binding type definitions, build caches,
   generated route types) are absent. `cp` them in during setup.
4. **Commit shared infrastructure to `main` BEFORE branching.** Uncommitted work on `main`
   does not propagate — worktrees branch from the commit, not the working tree. Test
   harness, configs, `.gitignore` entries, shared helpers: land them first, then branch.
5. **Validate the toolchain in one probe worktree before dispatching anything.** Create a
   throwaway worktree, run the repo's real gate there (typecheck, tests, build), fix what
   it finds on `main`, commit, re-probe, then branch for the real work. A toolchain that
   fails in the worktree burns every child's budget.
6. **Partition by FILE OWNERSHIP, not just by feature.** Two agents editing the same region
   of the same file is the only thing git cannot merge. Give each hot file one writer per
   wave, list the concurrently-edited files in every brief, and require minimal local diffs:
   no reformatting, no reordering, additions at clearly separated points.
7. **Every brief is self-contained.** A child sees nothing of your conversation: repo and
   worktree paths, sandbox quirks, exact verification commands, the codebase map, style
   rules, the project's guardrails, forbidden actions, and the commit + report format.
   Start from `templates/subagent-brief.md`.
8. **One `delegate_task` call, then end the turn.** Children run in the background and their
   results re-enter as messages; do not poll transcripts. Use the waiting time for work that
   does not depend on them.
9. **Merge one branch at a time behind the full gate.** Run typecheck + tests + build after
   EACH merge, not at the end — a red gate is trivially attributable when only one merge is
   in flight. Run the expensive build on the integration branch, not in every child.
10. **Children commit on their branch and never push.** Merge and push decisions stay with
    the operator, and unrequested pushes are never part of the job. Require a commit after
    each coherent step rather than one at the end — a child that dies mid-task otherwise
    leaves its work uncommitted and invisible on the branch.

## Procedure

1. **Recon.** Confirm repo, branch and a clean tree (`git status`). Check the runtime budget
   (cores, memory) — parallel builds on a small box mean staggering the heavy commands.
2. **Probe the toolchain** (rule 5), in the same session as the real work so you can fix
   what it finds immediately.
3. **Land the infrastructure on `main`**: test harness, configs, `.gitignore` entries, any
   helper the children will call. Commit with a descriptive message.
4. **Create the worktrees**, one command group per feature, and verify each one:

   ```bash
   git worktree add .worktrees/<name> -b feat/<name>
   ln -sfn ../../node_modules .worktrees/<name>/node_modules
   cp -n <generated-file> .worktrees/<name>/
   readlink .worktrees/<name>/node_modules   # silent setup failures are the common case
   ```

5. **Write the briefs** in one `delegate_task` call, one task per feature: goal, numbered
   required behaviour, files owned, files to leave alone, tests to add, and the exact
   verification commands with a requirement to report their output verbatim.
6. **End your turn.** Merge as results arrive.
7. **Merge each branch** (`git merge --no-ff feat/<name>`), resolving collisions as a neutral
   arbiter (see `merge-reconciler`), then run the gate. Fix forward on `main`, not on the
   child's branch.
8. **Report:** what merged, what the gate said, what was deferred and why. Never present a
   child's self-report as verified fact.

## When a child is interrupted

Children die mid-task (a session stop, a turn boundary, an operator interrupt) and the failure
is silent: the branch still points at the base commit while the worktree holds real,
uncommitted work. Recover before re-dispatching:

1. **Inventory every worktree** — `git -C .worktrees/<n> status --porcelain` and
   `git diff --stat` show what actually landed; run the repo's typecheck and tests to learn what
   is broken. Expect red: a half-finished feature usually leaves the gate failing.
2. **Commit the partial work immediately** as a labelled `WIP:` commit with explicit paths, so a
   second interruption cannot destroy it. A red typecheck is acceptable on a feature branch —
   the finisher's job is to make it green.
3. **Delete stray scratch/probe files** the interrupted run left behind before committing, or
   they ride into the merge.
4. **Re-dispatch a NARROWER finisher per branch**, not the original brief: name the branch and
   the WIP commit, paste the exact errors observed, list what is already done, and give the
   remaining checklist plus the commit-after-each-step rule. Narrow scopes finish before the
   next interruption window.

## Pitfalls

- **`git add -A` stages the `node_modules` symlink.** A `.gitignore` entry of `node_modules/`
  matches a directory, not a symlink, so the shared dependency tree shows as untracked in every
  worktree — stage explicit paths, in your own commits and in every brief.
- **Child claims are not evidence.** "Tests pass" from a child means it ran something; read
  the branch diff and run the gate yourself before telling the user it works.
- **Verification that needs live infrastructure cannot be done in a worktree.** Provisioned
  indexes, push credentials, real DNS, third-party APIs: scope that work out of the wave and
  say so, rather than merging code whose paths were never exercised.
- **Whole-file rewrites by children in hot files** produce conflicts that look like design
  disagreements. Rule 6 is the fix; when a feature genuinely needs a second pass over a hot
  file, put both passes in the same wave instead of serialising them across waves.
- **If a file-write tool comes back with a 0-byte file or a post-write verification error**,
  do not blind-retry: write through the shell (quoted heredoc) or use `scripts/fsedit.mjs`,
  which refuses ambiguous anchors instead of corrupting a file. Give children the same
  fallback in their brief.
- **A worktree is not a scratchpad for shared state.** Anything that mutates the shared
  `node_modules`, the git object store, or a global cache belongs on `main`.
- **Merging a branch whose tests were skipped** silently converts a red gate into a green
  one. Require the child's raw command output in its report and re-run the commands yourself.

## Support files

- `templates/subagent-brief.md` — the common brief skeleton every child gets.
- `scripts/fsedit.mjs` — stdin/snippet-based file writer and anchor-checked replacer for
  environments where the file tools cannot persist writes.
