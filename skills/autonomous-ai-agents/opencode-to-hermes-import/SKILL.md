---
name: opencode-to-hermes-import
description: "Use when importing/syncing opencode history into Hermes."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [opencode, hermes, migration, sessions, sqlite, import]
    related_skills: [opencode, hermes-agent]
---

# opencode → Hermes import

Migrates opencode history + projects into Hermes: sessions/messages into `state.db`
(source='opencode'), projects into `projects.db`. Full import: 622 sessions / 145,042 msgs /
38 projects / 0 errors (~100s across both stores).

## Run

- `cd ~/.hermes/scripts/opencode-import && ./run.sh` → dry run; `./run.sh --apply` → import.
- Idempotent: skips sessions already carrying `origin_json.imported_from.foreign_session_id` and
  projects whose primary folder exists. Re-run any time to sync new opencode sessions.
- Flags: `--limit N` (staged smoke test), `--tool-output-cap N` (default 1500), `--include-reasoning`,
  `--sessions-only` / `--projects-only`.
- Must run under the Hermes-bundled Python (needs `hermes_state*` modules): run.sh resolves
  HERMES_PYTHON from the hermes launcher; import_opencode.py re-execs itself if needed.
- Undo: `hermes sessions list --source opencode` → delete/prune by id; projects → `hermes project archive <slug>`.

## Source data model (opencode v2, verified on 2.0.12)

- DBs: `~/.local/share/opencode/opencode.db` (v2) and `opencode-stable.db` (legacy) — ALWAYS open
  with `mode=ro` (a server may be live). The two are disjoint; together they cover full history.
- Legacy store: same `session` table, but content lives in `message` + `part` rows (part types:
  text / reasoning / tool / step-start / step-finish / patch / compaction; tool parts use
  `callID` + `tool` + `state.output`; no `worktree` table — guard table lookups).
- `session_v2` = current sessions; `session`/`message`/`part` are legacy and fully covered by v2
  (verified: every legacy id present in v2). `session_message` ordered by `seq`; types:
  user / assistant / synthetic / idle / system / compaction / model-switched / location-switched.
- assistant rows: `content[]` parts of type text / reasoning / tool; tool parts carry
  `state.input` + result in `state.content[].text` (fallback `state.metadata.output`); terminal
  statuses only (completed/error).
- Empty shells titled "DSH session" have no rows anywhere — nothing to import.

## Mapping (what the script does)

- source='opencode'; provenance in `origin_json.imported_from` (foreign_session_id, model, cost, tokens).
- user→user; assistant text→content; tool parts→`tool_calls` + one role='tool' row per call (keeps
  replay-valid OpenAI shape); reasoning skipped by default; event/marker rows skipped.
- Consecutive same-role text merged (role-alternation invariant); tool sequences never merged.
- Titles: opencode title else first user line; dedupe with " #N" (Hermes title index is unique);
  set via `set_session_title`.
- Timestamps/tokens/cost/`end_reason='imported'` set via direct UPDATE after `create_session`
  (create_session stamps started_at=now and takes no timestamps).
- Children: `parent_session_id` mapped; create parents first (depth order) — FK-safe.
- Projects: name = `project.name` or basename(worktree); folders = worktree + project_directory +
  worktree rows; skip worktree '/'; `icon_color` carried over.

## Pitfalls

- Write via `hermes_state_registry.acquire()` + `append_messages_batch(chunk_rows≈200)` — the FTS5
  triggers index automatically; never raw-insert without them.
- Reasoning is NOT in FTS by design; keeping it in its own column keeps search clean and
  `--include-reasoning` roughly doubles db size.
- Size: 145k messages with a 1500-char output cap ≈ 479MB `state.db` (mostly FTS/trigram indexes).
  `hermes sessions optimize` compacts; a tighter re-import means deleting source='opencode' first.
- Always dry-run first; the dry run prints per-session counts and the project plan.
