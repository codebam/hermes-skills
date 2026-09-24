# Subagent brief skeleton

Fill every section. The child sees nothing of your conversation, so anything missing here is
missing work. Put this in the task's `context` field; put the deliverable in `goal`.

```
REPO: <absolute path> — <one-line stack summary>.
YOUR WORKTREE (work only here): <absolute path> on branch <branch>.
Do NOT push, do NOT merge, do NOT edit files in other worktrees or the main checkout.

SANDBOX QUIRKS: <e.g. file-write/patch tools may return 0-byte files — write through
`node .hermes/tools/fsedit.mjs write|replace|insert-after` with snippet files; read_file,
search_files and terminal work normally.>
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
Do NOT push.

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
