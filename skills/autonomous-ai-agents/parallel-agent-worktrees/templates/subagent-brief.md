# Subagent brief skeleton

Fill every section. The child sees nothing of your conversation, so anything missing here is
missing work. Put this in the task's `context` field; put the deliverable in `goal`.

```
REPO: <absolute path> — <one-line stack summary>.
YOUR WORKTREE (work only here): <absolute path> on branch <branch>.
Do NOT push, do NOT merge, do NOT edit files in other worktrees or the main checkout.

SANDBOX QUIRKS: <e.g. file-write/patch tools may return 0-byte files or silently insert
blank lines — write through a shell heredoc (python3 with exact anchors + asserts works
everywhere) and require `git diff --stat` after every edit; a diff larger than the intended
change means `git checkout -- <file>` and redo. read_file, search_files and terminal work
normally.>
Do NOT run `npm install` (node_modules is shared via symlink) and add no new dependencies.
Do not touch <lockfiles / manifests>.

TOOLCHAIN (verified, exact commands):
- `<typecheck command>` (must exit 0)
- `<test command>` (must pass; keep existing tests green; add <tests/path>)
- Do NOT run `<expensive command>` — the parent runs it after merging.

CODEBASE MAP: <files the child must read first, one clause each: where routes live, where
storage lives, where shared logic lives, where UI lives, the conventions to follow.>

CONCURRENCY: other agents are editing <hot files> in parallel worktrees. Make minimal LOCAL
diffs: never reformat, reorder, or clean up unrelated code. Add at clearly separated points.

STYLE RULES: <indentation, quote style, import order, UI component library, comment banners.>

GUARDRAILS (do not weaken): <the invariants of this codebase — e.g. validation runs on every
write path; the agent never performs the destructive action without explicit operator intent.>

COMMIT when done: `git add <specific paths>` (never `git add -A`), sentence-style message.
Do NOT push. If the repo's pre-commit hook runs a full build or the test suite, commit with
`git commit --no-verify` — the parent runs that gate at merge time.
No git identity configured? Match the repo's existing author
(`git log -1 --format='%an <%ae>'` shows it) and pass it per-command as GIT_AUTHOR_NAME/EMAIL
and GIT_COMMITTER_NAME/EMAIL — never write it into `.git/config`. (If the parent session found
no identity anywhere, it may instead set the repo-local identity once to that same author and
disclose it in the report — then children commit plainly and need no extra flags.)

REPORT BACK (concise): files changed; exact commands run with their raw results
(typecheck / tests); anything skipped or impossible.
```

## goal

Numbered, testable required behaviour — one line per requirement, each naming the observable
outcome (route, field, UI affordance, semantics). Name the tests to add. End with the
verification requirement: "before you finish, <typecheck> exits 0 and <tests> pass; report
the exact commands and results."

## Notes

- Requirements that need live infrastructure (provisioned indexes, credentials, DNS) do not
  belong in a worktree wave. Leave them out and tell the operator they are deferred.
- If the feature touches a hot file another child also owns, say explicitly which functions
  are yours and which are theirs.
