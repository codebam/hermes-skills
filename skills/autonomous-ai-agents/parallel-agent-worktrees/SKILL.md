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
change you would just make yourself — with one exception: when another writer is already
mid-flight in the same repo (a running agent, an uncommitted tree on `main`), a one-file change
still gets its own worktree and you do it yourself. Isolation is about concurrent writers, not
about batch size: check what the in-flight branch owns (`git diff --stat main <branch>`,
`git -C .worktrees/<n> status --porcelain`), keep your diff off those files, commit on your
branch, then merge behind the full gate like any other change.

## When to Use

- A batch of independent changes ("do these five features", "implement 2, 4, 5, 3, 1") where
  each one can be built and gated on its own branch.
- Any change at all — even a single small file — while another writer is mid-flight in the same
  repo.
- Not for one small change on a clean tree with no other writer: make it yourself.

## Non-negotiables

1. **Worktrees live inside the workspace, never beside it.** A sandboxed or bind-mounted
   workspace does not expose sibling directories: `git worktree add ../wt-x` creates a path
   the agents then cannot see or build in. Use `<repo>/.worktrees/<name>` and add
   `.worktrees/` to `.gitignore` before creating any.
2. **Symlink the dependency tree, never install per worktree.**
   `ln -sfn ../../node_modules .worktrees/<n>/node_modules` keeps one shared `node_modules`
   serving every branch. Ban `npm install` in every brief — one child installing into the
   shared symlink corrupts every sibling mid-run. The link points at the HOISTED tree, which
   in a submodule monorepo lives in the parent repo: a worktree inside a submodule needs
   `../../../node_modules`, a worktree of the parent repo needs `../../node_modules`. Count the
   levels per repo and confirm each with `readlink` — a wrong depth fails as a missing binary
   in the child, not as a symlink error.
3. **Copy gitignored generated files into each worktree.** A fresh worktree checks out
   committed files only, so generated artifacts (binding type definitions, build caches,
   generated route types) are absent. `cp` them in during setup. That includes your own
   untracked helper scripts that briefs tell children to use (an anchor-checked edit helper
   kept under the repo's ignored `.hermes/tools/`, say): `cp` it in during setup or put the
   copy command in the brief — a child told to run a path that does not exist on its branch
   burns a turn inventing a workaround for it.
4. **Commit shared infrastructure to `main` BEFORE branching.** Uncommitted work on `main`
   does not propagate — worktrees branch from the commit, not the working tree. Test
   harness, configs, `.gitignore` entries, shared helpers: land them first, then branch.
   The same applies to any source file compiled into more than one child's program (a
   workspace-linked shared package, a common types file): fix it on `main` first, or every
   child's typecheck shows the identical errors in that one file, every child is tempted to
   edit it, and no branch can go green on its own. When that cross-cutting file is itself part
   of the sweep rather than a prerequisite, give it its own writer in its own worktree and mark
   it off-limits in every other brief; keep its changes type-level so no consumer's program
   changes shape.
5. **Validate the toolchain in one probe worktree before dispatching anything.** Create a
   throwaway worktree, run the repo's real gate there (typecheck, tests, build), fix what
   it finds on `main`, commit, re-probe, then branch for the real work. A toolchain that
   fails in the worktree burns every child's budget. Once `main` itself has been fully gated at
   the exact commit you are branching from, the per-wave probe can be cheap instead: one fast
   spec run inside a real child worktree (same harness, and it also proves that worktree's
   symlink and generated files) plus the typecheck when the wave's other child owns a different
   half of the toolchain. A full throwaway probe per wave is minutes you do not get back.
   Whichever probe you run, seed the sibling worktrees from the probed worktree's freshly
   generated artifacts (binding types, route types, build caches) before dispatching: the probe
   worktree is the only one that has executed the generation step, and a child whose first
   command is a scoped lint or typecheck otherwise starts against missing generated types.
6. **Partition by FILE OWNERSHIP, not just by feature.** Two agents editing the same region
   of the same file is the only thing git cannot merge. Give each hot file one writer per
   wave, list the concurrently-edited files in every brief, and require minimal local diffs:
   no reformatting, no reordering, additions at clearly separated points. Shared registries —
   migration arrays, route tables, enum/union types, config lists — are serialization points
   even when the file is not otherwise hot: assign each child its own slot up front (an
   explicit migration number AND name, its own entry), forbid renumbering or reordering, and
   have everyone append at a defined point so the eventual merge is a keep-both. Before
   letting two writers share a file, measure the disjointness instead of assuming it: extract
   each change's line numbers and compare the sets. Line sets separated by several lines of
   context auto-merge; changes on adjacent lines (two settings in one config object, two arms
   of one expression) will not — give that whole file a single writer.
7. **Every brief is self-contained.** A child sees nothing of your conversation: repo and
   worktree paths, sandbox quirks, exact verification commands, the codebase map, style
   rules, the project's guardrails, forbidden actions, and the commit + report format.
   Start from `templates/subagent-brief.md`. Do the integration recon yourself and paste the
   anchors into the brief — file plus a distinctive symbol or string, never a bare line number,
   which drifts — so a child starts building instead of searching. Name the machinery it must
   EXTEND (the existing timer, its arming helper, the sweep that backstops it, the shared
   registry whose slot it owns) and forbid a parallel one, or a child will invent a second
   scheduler beside the one already there.
8. **One `delegate_task` call, then end the turn.** Children run in the background and their
   results re-enter as messages; do not poll transcripts. A background-process completion notice
   that names a child's process (the child ran a long build or test in the background) is NOT that
   child's result — the delegation result arrives as its own message, so acknowledge the notice and
   keep waiting. Use the waiting time for work that does not depend on them.
9. **Merge one branch at a time behind the full gate.** Run typecheck + tests + build after
   EACH merge, not at the end — a red gate is trivially attributable when only one merge is
   in flight. Run the expensive build on the integration branch, not in every child. Never
   resolve a conflicted file by taking one whole side (`git checkout --ours/--theirs <file>`):
   that discards the hunks git already auto-merged, and the loss surfaces as a failure in a
   feature you merged EARLIER. When a resolution combines two features' hunks, re-run the
   tests of BOTH features — the merged combination is the thing that breaks.
10. **Children commit on their branch and never push.** Merge and push decisions stay with
    the operator, and unrequested pushes are never part of the job. Require a commit after
    each coherent step rather than one at the end — a child that dies mid-task otherwise
    leaves its work uncommitted and invisible on the branch.
11. **A file owned by an unmerged branch is off-limits to the next wave.** While an earlier
    wave's branch is still in flight, its files — entry points, config, the new modules it
    introduced, its migration slot — belong to it alone. List them in every brief with the
    reason. A wave that respects the list merges without conflict; one that edits them either
    collides at merge time or silently re-implements the feature already in flight.
12. **Freeze the seam between siblings in both briefs, and let each half compile alone.** Where
    two branches meet (a producer that owns the shared constants, a consumer that renders or
    calls them), write the seam into BOTH briefs verbatim — exact column names, route paths,
    method signatures, response shapes, identifier ids — so neither child has to guess what the
    other is building. The consumer must not import the producer's new symbol, which does not
    exist on its branch yet: have it keep that id in ONE local constant in one file, and repoint
    the constant at the shared one yourself on `main` after the merge. Both halves then
    typecheck and merge clean, and the duplication lives for exactly one merge. But a frozen seam
    does not verify itself: the wire names BETWEEN the halves are the one thing no gate on either
    side can see. A request-body key and a response envelope are strings, so a consumer posting
    `sendAt` against a route reading `send_at`, or typing a bare row where the route answers
    `{ send: row }`, compiles, lints and passes both suites — and fails only as a 400 or an
    `undefined` field at runtime, in the path the operator exercises first. Before merging the
    pair, grep the consumer for the keys it sends and the shape it reads, diff them field by field
    against the producer's request schema and response literals, and fix any drift on the
    consumer's branch as its own commit naming the contract. When the wave has several producer/
    consumer pairs, do this for each pair before its merge — the gate after the merge cannot
    catch it either, because both halves are individually consistent.
13. **A wave that consumes the previous wave's new symbols goes out after that wave MERGES.**
    Same-session wave 2 is normal, but its children compile against the producer's methods and
    assert against its real surface, so dispatching them in parallel with wave 1 hands them
    symbols that do not exist yet. Send the consumer wave as a single-writer dispatch once the
    producer is on `main` — and when its tests pin an exact surface (a tool-name list, a route
    table) that two children would both have to edit, that shared list is one more reason to
    serialise rather than a file to share.

## Procedure

1. **Recon.** Confirm repo, branch and a clean tree (`git status`). Map the repo layout before
   planning anything: `cat .gitmodules` and `git ls-files -s | grep '^160000'` reveal submodules,
   and `ls -d */node_modules packages/*/node_modules` shows where dependencies actually live
   (hoisted root vs per-package). In a repo with submodules each submodule is its own repo —
   its worktrees go inside that submodule's directory, its branches merge into that submodule's
   branch, and the parent repo's gitlink pointer stays stale until the operator commits it (say
   so in the report). Check the runtime budget (cores, memory) — parallel builds on a small box
   mean staggering the heavy commands. Read `git config --get core.hooksPath` and the hook
   bodies in every repo the wave touches: a pre-commit hook that runs the full build or test
   suite turns each child commit into a long, fragile step — brief children to commit with
   `--no-verify` and keep that build as the parent's merge gate. Confirm a committable git
   identity too (`git log -1 --format='%an <%ae>'` shows the repo's author): a missing one
   surfaces only as a failed commit at the END of a child's run, after its whole budget is spent.
   Read the authoritative plan for this work (`.hermes/plans/*`) and record the operator's item
   numbering in it against the plan's own section numbers: the shorthand order he names is
   usually his ranked list, not the plan's table order, and rebuilding that mapping after a
   context compaction is pure loss.
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
   arbiter (see `merge-reconciler`), then run the gate. A producer/consumer pair also needs its
   wire-contract check before either half merges (rule 12) — the gate cannot see it. Fix forward
   on `main`, not on the
   child's branch. Remove the worktree once its branch is merged
   (`git worktree remove .worktrees/<n> --force`): a stale worktree keeps claiming its files
   under rule 11 and its `node_modules` symlink lingers — and sweep leftovers from EARLIER
   sessions at the start of a wave, not only the branch you just merged. Confirm merge by
   ancestry first (`git merge-base --is-ancestor <branch> main`, or an empty
   `git log main..<branch>`) and `rm -f .worktrees/<n>/node_modules` before the remove: the
   symlink alone reads as `?? node_modules` in `status --porcelain`, which is how a fully
   merged leftover gets left behind as "dirty".
8. **Report:** what merged, what the gate said, what was deferred and why. Never present a
   child's self-report as verified fact. Keep the plan's wave log current — item → state →
   landed commits, plus the design decisions taken while implementing (semantics chosen, the
   module a later feature should reuse) — so the next wave or session inherits them instead
   of re-deriving them.

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

- **Never put an unverified CLI flag in a brief.** Probe the exact command in the probe
  worktree first: a flag can be gone from the installed major version (`eslint -f unix` was
  removed in ESLint 10) and every child then burns a turn reporting the tool as broken while
  second-guessing its own result. If the tool's version matters, say the version in the brief.
  The same holds for a library export a brief tells a child to use: grep the installed package
  before naming it — a helper that is not in this version (no `fetchMock` in the vitest pool,
  for instance) sends the child hunting a workaround instead of building the seam the codebase
  actually needs. The rule covers a codebase premise as well: grep for the field, column or
  storage path the feature is meant to read before you describe a design around it — a brief
  that assumes "the header is already stored" when the ingest path never persists it buys the
  child a design detour and the wave a re-brief. A premise about a CHOKE POINT needs the same
  treatment one level deeper: when the brief says "hook the single place X happens", grep every
  call site of the underlying side-effecting function and confirm they all route through it — a
  path that bypasses the choke point makes the feature silently incomplete for exactly the
  traffic nobody tests (an outbound send path that skipped the stored Sent copy, so a
  contacts/audit feed never saw rule-driven mail). Put the audit IN the brief ("verify every
  `sendEmail(` call site stores a Sent copy; hook any that does not") — a child told to hook a
  choke point otherwise wires the happy path and stops. A RUNTIME premise (an SQL feature, a
  tokenizer, a platform binding) is the same class of risk one level lower: probe it in the real
  runtime with a throwaway spec before a brief asserts it, and paste the measured result into the
  brief so no child re-derives it or second-guesses its design (`cloudflare-workers-testing` →
  `references/do-sqlite-fts5.md` is an example of the evidence shape).
- **A brief must not carry a placeholder marker — the dispatch is refused.** `delegate_task`
  validates the goal/context text and rejects an unexpanded `<...>` template token
  ("unexpanded template marker"); one such token aborts the whole call and every task has to be
  re-sent. Write every list and value out (the exact columns, the exact route), and reword
  quoted shell commands that would otherwise contain bracketed metavariables ("the paths you
  touched", not a bracketed placeholder).
- **A workspace-linked shared package merges FIRST, and its consumers re-run their gate.**
  When sibling packages compile the shared source directly (`exports` pointing at `src/`),
  a type change there lands on the consumers at merge time, not at branch time: a child that
  removed casts while the shared type was `any` gets contravariance errors the moment the
  shared branch merges. Merge the shared package, re-run each consumer's typecheck on the
  integration branch, and fix forward there (method syntax on an interface property keeps
  parameter checking bivariant where `any` used to).

- **Children on a shared box report contention as product bugs.** State in every brief that
  siblings are running builds and tests at the same time, and that a timed-out or killed
  command is re-run before it is called a failure — otherwise the wave's reports fill with
  phantom breakage and children start "fixing" code that was never broken.
- **Browser-mode vitest does not run in the opensandbox container; headless Chromium does.**
  `npx vitest run` dies with `ENOSPC: System limit for number of file watchers reached` (Vite's
  watcher); `CHOKIDAR_USEPOLLING=1 npx vitest run ...` gets past that, but a browser-mode spec
  still fails to launch a browser through Playwright. Make the typecheck (svelte-check / tsc) the
  gate for worktree children and say in the brief that browser specs will not run there. What
  the gate cannot cover is how a page or asset actually looks — probe `command -v chromium`:
  when present it renders headlessly (`--headless --no-sandbox --disable-gpu`) and answers CDP,
  which is enough to screenshot a page under an emulated `prefers-color-scheme` (ready script:
  the `agentic-inbox` skill's `scripts/cdp-scheme-shot.mjs`) or to pixel-count a colour
  assertion. Headless has no browser chrome, though: an asset's real appearance in the tab strip
  needs a windowed browser (`Xvfb` + `scrot`), and what the operator sees there is browser UI,
  not page content — the `browser-chrome-assets` skill carries that harness. Never report a look
  you did not render. Expect a worktree dev server to serve SSR HTML while the CLIENT bundle is
  refused by Vite's fs allow-list (`entry.client.tsx` resolves outside the symlinked root):
  enough to verify head markup and inline scripts, not a hydrated page.
- **Check `prettier --check` before prescribing `prettier --write`.** A file can be
  non-conformant at HEAD, so `--write` reformats regions the child never touched and its diff
  stops being local. Name the already-dirty files in the brief and have the child hand-format
  its own lines instead (verify by re-running `prettier --check` and confirming only the
  pre-existing hunks remain).
- **`git add -A` stages the `node_modules` symlink, and undoing that commit can delete the real
  tree.** A `.gitignore` entry of `node_modules/` matches a directory, not a symlink, so the
  shared dependency tree shows as untracked in every worktree. Fix the cause once, on `main`:
  put a bare `node_modules` line beside the slashed one, so `git add -A` cannot stage the link
  in any worktree. Stage explicit paths in your own commits and in every brief regardless.
  If the symlink does get committed, never undo it with `git reset --hard`: the commit tracks
  that path, so the reset deletes the working-tree entry — and the real `node_modules`
  directory it points at goes with it, taking every sibling worktree's toolchain down at once.
  Strip the path instead (`git rm --cached node_modules` + `--amend`, or a rebase whose
  `--exec` amends each affected commit), then `ls node_modules` in the main checkout, and
  recover a deleted tree with `npm ci` (lockfile-exact) rather than `npm install`.
- **Sweep waves (lint / typecheck error inventories) are sized, not guessed.** Tally the
  inventory per file and per rule before partitioning it, and never paste the raw error list
  into a brief — the commands, the partition rules and the brief contents are in
  `references/sweep-wave-sizing.md`.
- **Child claims are not evidence.** "Tests pass" from a child means it ran something; read
  the branch diff and run the gate yourself before telling the user it works. Check the exit
  status, not the test count: a runner can print a fully green suite and still exit non-zero
  (test pools report platform-level errors beside passing tests), and a child reading only
  the summary will report it green. Two cheap checks before merging: `git -C .worktrees/<n>
  diff --stat <base>..HEAD` against the file list the brief assigned — a path outside its
  ownership is a conflict waiting for the next wave — and the suite's file/test count against
  the base, because a passing run with an unchanged count means the new tests were never
  collected. Third check, when the brief told the child to extend a strict-equality contract list
  (an exact tool-name list, a route table, a permission map): diff that list and require the
  change to be ADDITIVE. Deleting a stale entry also turns the assertion green, and only
  `git diff <base>..HEAD -- <that file> | grep '^-'` catches it. The same removal-grep over the
  whole test diff (`git diff <base>..HEAD -- tests/ | grep '^-'`) is the check for coverage
  quietly dropped: read every removed test line and require it to be a deliberate semantics
  change the brief asked for, because a deleted assertion is the other way a red suite turns
  green. Read the security-critical and
  state-machine hunks YOURSELF whatever the report says — an SSRF guard, an undo/restore path,
  the arm/drain handler, a fire-time re-check — because a plausible-looking implementation there
  is wrong in a way the author's own tests will not catch; skim the rest against the diffstat.
- **A justified change outside a child's file list is verified, not rejected.** Children
  sometimes have to touch a file the brief did not name (a shared store that must carry a new
  field, a helper the feature cannot work without). The diff check is what catches the path;
  then read the child's stated reason and confirm it by grepping the affected call sites —
  accept only when no existing caller's behaviour changes, and say in the report that you
  checked. Rejecting it outright discards a necessary fix; taking the child's word for it is
  how an unrelated behaviour change rides into the merge.
- **Verification that needs live infrastructure cannot be done in a worktree.** Provisioned
  indexes, push credentials, real DNS, third-party APIs: scope that work out of the wave and
  say so, rather than merging code whose paths were never exercised.
- **Whole-file rewrites by children in hot files** produce conflicts that look like design
  disagreements. Rule 6 is the fix; when a feature genuinely needs a second pass over a hot
  file, put both passes in the same wave instead of serialising them across waves.
- **If a file-write tool comes back with a 0-byte file or a post-write verification error**,
  do not blind-retry: write through the shell (quoted heredoc / python with exact anchors and
  asserts) or use `scripts/fsedit.mjs`, which refuses ambiguous anchors instead of corrupting
  a file. Give children the same fallback in their brief. The corruption can also be silent —
  a "successful" write that inserts spurious blank lines across the file — so make
  `git diff --stat` after every edit part of the brief: a diff larger than the intended change
  means `git checkout -- <file>` and redo through the shell. Recover by restoring from git
  first, never by hand-cleaning the corruption.
- **A worktree is not a scratchpad for shared state.** Anything that mutates the shared
  `node_modules`, the git object store, or a global cache belongs on `main`.
- **Merging a branch whose tests were skipped** silently converts a red gate into a green
  one. Require the child's raw command output in its report and re-run the commands yourself.
- **Prove merge state with ancestry, not with a diff.** `git merge-base --is-ancestor <sha>
  main` (or `git branch --contains <sha>`) answers "is this branch merged"; `git diff main
  <branch>` does not — once main moves ahead (someone else's merge landed), that diff lists
  MAIN's own newer commits and reads like the branch still holds unmerged work, which is how a
  merged branch gets re-reported as pending. `git log --oneline --ancestry-path <sha>..main`
  names the merge that carried it in.

## Support files

- `templates/subagent-brief.md` — the common brief skeleton every child gets.
- `scripts/fsedit.mjs` — stdin/snippet-based file writer and anchor-checked replacer for
  environments where the file tools cannot persist writes.
- `scripts/resolve-conflict-blocks.mjs` — list a conflicted file's blocks, then replace them
  from an ordered plan; refuses to write when the plan and the file disagree.
- `references/hunk-resolution-mechanics.md` — the extract / `git merge-file` / plan / apply
  recipe for resolving conflicts hunk by hunk without losing auto-merged changes.
- `references/worktree-toolchain-setup.md` — making a fresh worktree pass the real gate:
  dependency-tree symlink depth, generated artifacts per stack, framework-generated packages
  with relative paths (SvelteKit `$app`), and the probe-worktree recipe.
- `references/sweep-wave-sizing.md` — inventorying an existing lint/typecheck error backlog
  machine-readably, tallying it per file and per rule, and partitioning it across children.
