---
name: agentic-inbox
description: Use when working on the agentic-inbox email app.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [agentic-inbox, cloudflare-workers, durable-objects, email, project]
    related_skills: [cloudflare-workers-testing, parallel-agent-worktrees, feature-gap-analysis]
---

# agentic-inbox

A self-hosted email inbox on Cloudflare Workers: Hono API, React Router 7 UI, one Durable
Object with SQLite per mailbox, R2 for attachments, Workers AI for classification and drafting.
Repo `/home/codebam/Documents/git/agentic-inbox` on this machine — confirm paths with grep,
they move. Subsystem index: `references/architecture-map.md`.

## Guardrails (never break these)

- **No send path on the agent or MCP tools.** Drafting is unrestricted; sending, replying, or
  forwarding from the agent/MCP is the one thing the design forbids. When adding rule actions
  that send (forward, auto-reply), keep them out of the agent/MCP rule tools entirely — those
  actions exist for automations the operator authored.
- **`verifyDraft` stays on every outbound path** (draft, reply, forward, MCP).
- **Spam stays undraftable**, and a blocked sender's mail is still stored in Spam — never
  silently dropped.
- **Trash semantics**: `delete` is trash-aware (already in Trash → purge, otherwise → Trash);
  permanent purge only from Trash or via an explicit `permanent` flag.
- **Sender-controlled URLs get one guard, and stay click-only.** Any Worker-initiated fetch to a
  URL taken from message content — one-click unsubscribe (no body read) and the remote-image
  proxy (image mode, capped) — goes through the single shared module
  `workers/lib/ssrf-guard.ts`: https only, no credentials in the URL, no IP-literal or
  `localhost`/`.local`/`.internal` host, port 443/8443 only, redirects refused, a timeout. The
  action fires on an explicit operator click and never on render — and it is deliberately NOT
  exposed as an agent or MCP tool, so no model can fire a sender-controlled request.
- **Remote images never load from the sender's servers.** After opt-in the body is rewritten to
  the same-origin route `/api/v1/mailboxes/<id>/image-proxy?url=` and the iframe CSP is
  `data: cid: <appOrigin>` in BOTH modes — `https:` is never allowed again, so a proxy-refused
  image (http-only, over 5 MiB, outside the type allowlist, never SVG) renders broken instead of
  loading directly. Bytes cache in R2 under `image-proxy/` (key: sha256 of the URL) with a
  30-day cron sweep. A new remote-media path extends `ssrf-guard`'s image mode and the rewrite
  helper in `shared/remote-images.ts` — it never grows a second fetch.

## Verify, then deploy

- Gate every change (in the worktree AND again on `main` after merging):
  `npm run typecheck` → 0 · `npx vitest run` → 0 with all files · `npm run lint` → 0 ·
  `npm run build` → 0.
- ESLint (`eslint.config.js`, flat) is type-aware for `app/`, `workers/`, `shared/` and the
  root config files; `tests/` and `scripts/` belong to no tsconfig, so they get syntax-level
  rules only (making the test suite type-checked is a separate ~150-error job). In a parallel
  wave the lint gate is repo-wide, so scope each child's check to its own paths:
  `npx eslint <paths> --max-warnings 0`.
  `.worktrees/**` must stay in that config's `ignores`: a worktree is a full copy of the
  codebase, and linting the repo root with a few present makes ESLint build a program per
  tsconfig project and abort with an out-of-memory core dump (760 vs 133 TS files). `eslint .`
  and `eslint <dir>` can also disagree on the same file — `projectService` builds different
  programs — so verify a slice with the repo-wide command before calling it clean.
- `npm run deploy` is `npm run build && wrangler deploy`. Nothing else to run afterwards: DO
  SQL migrations apply inside the `MailboxDO` constructor on each mailbox's next request, cron
  triggers and wrangler-level DO migration tags ride the deploy. There is no D1 in this app, so
  `wrangler d1 migrations apply` is never part of the procedure.
- Production fails closed without the `POLICY_AUD` and `TEAM_DOMAIN` secrets (Cloudflare
  Access): a 403 "Access must be configured" means they are missing, the Access redirect means
  they are fine. Neither identifies the live build: `wrangler deployments list` carries the
  deploy timeline (oldest first — the newest deploy is the last entry), and the live-bundle
  fetch below says which features the build actually contains — deploys here carry no commit
  metadata.
- **"Is it live?" is answerable from evidence.** Fetch the running script through the
  Cloudflare API (`/workers/scripts/<name>/content/v2`; the OAuth token is already at
  `~/.config/.wrangler/config/default.toml`) and count markers only the new code carries
  (table names, tool names, header strings). Recipe + script:
  `cloudflare-workers-testing` → `scripts/live-worker-markers.py`. Read-only wrangler/API
  access exists when the session's terminal runs on the host shell; the deploy itself stays
  the operator's step.
- Mechanics live elsewhere: `cloudflare-workers-testing` for the pool and deploy details,
  `parallel-agent-worktrees` for multi-feature waves.

## Working conventions

- Features go through worktrees: `git worktree add .worktrees/<name> -b feat/<name>`, then
  symlink `node_modules` from the repo root (never `npm install` inside a worktree) and copy
  the gitignored helpers in — `.hermes/tools/fsedit.mjs` (edit through it, or a quoted heredoc,
  and verify the byte count, since a write that reports success can land empty here) and
  `.hermes/tools/ts-error-sources.mjs` (error triage). None of these are tracked, so a fresh
  worktree has none until you copy them. Also copy the other gitignored artifacts a worktree
  lacks — `worker-configuration.d.ts`, `.react-router/`, the `*.tsbuildinfo` files — so a
  child's first scoped lint/typecheck sees real generated types (`npm run typecheck`
  regenerates them, but a child's first `npx eslint` does not).
- Trust the compiler over the file viewer: `read_file`'s line numbers DRIFT from the real file
  (seen up to ~4 lines off), so locate code by content anchor, never by a line number read
  elsewhere. `node .hermes/tools/ts-error-sources.mjs <flag>` runs tsc with a strictness flag
  forced on and prints every error joined to its REAL source line — use it for error triage.
- `write_file`/`patch` frequently report "Post-write verification failed ... The patch did not
  persist" while the write DID land. Confirm with a raw read (`node -e` regex test on the file)
  before re-sending, or edit through `.hermes/tools/fsedit.mjs`, which is anchor-checked and
  fails loudly instead of corrupting. The tool also hard-REFUSES some writes outright
  (`stale_write_blocked`, or "last read with offset/limit pagination") when it has not seen the
  file's full current content at that exact path — a refusal means nothing was written, so do
  not answer it with another read/retry loop: pipe the content in from a quoted heredoc with
  `node .hermes/tools/fsedit.mjs write <path>` and check the byte count it reports. The
  auto-lint a write triggers is a repo-wide `tsc` without the generated worker types, so it
  answers with hundreds of unrelated errors — when that noise is not wanted, create or rewrite
  a `.ts` file through a `node` script (`fs.writeFileSync`) or a `/tmp` snippet plus fsedit
  instead of `write_file`.
- **Multi-file edits: one script, asserted anchors.** Hold every edit in a single `node` script
  as an `{file, old, new}` triple, count occurrences of `old` first and refuse unless it is
  exactly 1, then apply them together — a partial apply can then never pass for success, and a
  missed anchor names the edit instead of silently doing nothing. When the exact indentation is
  uncertain, do not embed tabs in the anchor: find the line by a distinctive substring and
  insert relative to it (or to the first closing line after it). Tab depth counted from a
  `read_file` view is wrong often enough that anchors silently miss, and every miss costs a
  round-trip.
- Untracked scratch directories (e.g. a local `.tsprobe/`) do not survive here — keep throwaway
  configs and outputs under `/tmp`, or expect to recreate them.
- Migrations are append-only: add a new numbered entry at the END of `mailboxMigrations`
  (`<n>_<what>`) and mirror it in `workers/db/schema.ts`; never renumber. In a parallel wave,
  assign each branch its own number and name. A wholesale purge (`deleteAll()` on the mailbox
  DO) must re-apply the migrations in the same call — the constructor does not re-run on a live
  instance — and the purge order is data first, listing marker last, so a failure part-way
  leaves the mailbox listed and the delete retryable.
- **Due-work features ride the Durable Object alarm, not a new timer.** A DO alarm is
  single-valued, so a second feature calling `storage.setAlarm()` silently cancels the first
  one's schedule: a new due-work feature extends the existing arm/drain path — add its table to
  the earliest-due computation (`#nextDueAtMs`), its drain to `alarm()`, and its work to the
  daily cron sweep that backstops them. Arming only ever moves the alarm EARLIER, and the handler
  re-arms after draining. Snooze/reminder state
  machine: pending = `remind_at` set, fired = `reminded_at` set; a snoozed message sits in the
  `snoozed` system folder and wakes back into the folder it came from — new mail in that thread
  wakes it early, and a reply cancels the thread's reminder.
- Hot files (`workers/index.ts`, `workers/durableObject/index.ts`, `workers/lib/schemas.ts`,
  `app/services/api.ts`, the settings/list/panel components): call into a new module from one
  line, put new UI in new component files.
- **Header-driven features must parse at ingest — inbound mail stores no `raw_headers`.** Only
  the outbound paths persist them, so a header the app should act on later (List-Unsubscribe
  today; calendar invites, DSNs) is extracted in `receiveEmail` from the parsed message, carried
  through `EmailData` and stored in its own column. Check `grep -n raw_headers workers/index.ts`
  before assuming a header is queryable.
- **Cross-cutting bookkeeping hooks `createEmail`, and that "one choke point" premise must be
  audited per path.** The store-side choke point is `MailboxDO.createEmail`, so feeds hang off it
  in a try/catch (a bookkeeping failure must never fail message storage): the `contacts` store
  (`workers/lib/contacts.ts`) upserts by lowercased address from it — a Sent copy counts
  recipient/cc/bcc as sent, any other folder counts the sender as received — and prunes to the
  newest 5000. But the premise only holds for paths that route through it: grepping every
  `sendEmail(` call site showed rule-driven forwards and auto-replies
  (`workers/lib/rule-outbound.ts`) never stored a Sent copy at all, so they were invisible in the
  mailbox and absent from contact counts until they were given one (best-effort and logged, so a
  storage failure cannot flip the attempt to failed or skip the auto-reply cooldown). Audit the
  call sites before building anything that counts or observes outbound mail — bounce/DSN state,
  delivery badges and quota rollups will hit the same trap.
- **Prefix search in mailbox SQL is `substr(LOWER(col),1,length(?)) = ?`, never `LIKE`.** It keeps
  `%`/`_` literal in operator input and sidesteps LIKE's pattern limits; ranking is
  `sent_count DESC, received_count DESC, last_seen_at DESC`. Contacts stay metadata only (address,
  display name, counts, timestamps), are served by `GET /contacts` and `search_contacts` on both
  tool surfaces (the recipient-resolution tool), and back the composer's To/Cc/Bcc autocomplete.
  For full-text search, DO SQLite does support FTS5 — external-content tables, `rebuild`,
  column-scoped sync triggers and the trigram tokenizer are all verified in this runtime; the
  measured matching behaviour, escaping rules and the throwaway-probe recipe live in
  `cloudflare-workers-testing` → `references/do-sqlite-fts5.md`. Mailbox search itself runs on
  `emails_fts` (external-content over `emails`, trigram, sync triggers; migration 23) — a new
  searchable column or filter extends the index + its triggers + `workers/lib/fts-terms.ts`,
  never a fresh `LIKE` scan: 3+ char terms become quoted FTS phrases, 1-2 char terms stay on the
  LIKE path, and the query's term count is capped.
- **Retroactive rule apply is local-actions-only and idempotent.** `applyRuleToExisting` /
  `POST /rules/:id/apply` run only folder/category/read/starred against stored mail — `discard`,
  `forward_to` and `auto_reply_text` are never retro-applied (retro-sending about old messages
  is the guardrail violation), and a rule with no local action is a 400. Matches already in the
  target state count as `skipped`, so a repeat call applies 0 and the UI's apply-until-done loop
  terminates; batches clamp to 90 with `remaining` reporting the overflow; no firing-stats bump,
  no tool. It and `previewRule` scan through the SAME window helper — a new rule condition or a
  changed scan window belongs there, not in a second scan.
- **Templates are per-mailbox rows with reject-don't-clip bounds.** `templates` (migration 24):
  name ≤ 120, subject ≤ 500, body ≤ 100k, at most 200 per mailbox; a violating create/update is a
  400-class error, never silently truncated. The composer picker
  (`app/components/TemplatePicker.tsx`) inserts a body (subject only when the composer's is
  empty), saves the draft as a template, and deletes a row; the only tool surface is the
  read-only `list_templates` on agent and MCP.
- **A new agent/MCP tool means editing `tests/tool-parity.test.ts`.** It pins the exact agent and
  MCP tool-name lists and asserts the MCP list against a live `/mcp` handshake, so a missing name
  (or a registration typo) fails the gate rather than drifting silently.
- **Every mutating agent/MCP tool call is audited, and the wrapper sits at the SURFACE.** `runAudited`
  (`workers/lib/agent-actions.ts`) is wrapped around the call in `workers/agent/index.ts` and
  `workers/mcp/index.ts`, never inside the shared functions in `workers/lib/tools.ts` — that is what
  keeps `source` ('agent' vs 'mcp') unambiguous and the tool signatures unchanged. Rows are metadata
  only (bounded JSON, never bodies), live in the mailbox's `agent_actions` table, and are pruned to
  the newest 500 on insert. `undoable` is set only for the reversible three (move/star/read) and only
  when a before-state was actually captured — `delete_email` is recorded but never undoable — and undo
  restores all three fields from that action's snapshot, so undoing an OLDER action also reverts a
  later change to them (deliberate, pinned by a test). Adding a mutating tool is therefore two edits:
  the tool itself plus its `runAudited` wrapper on both surfaces. New per-mailbox tables follow this
  shape generally: metadata-only rows plus a prune-on-insert bound.
- **UI code must be render-pure: `react-hooks/purity` rejects `Date.now()` in a component body.**
  Preset times, "today" boundaries and anything else clock-derived are computed in event handlers
  or derived callbacks, never during render — the rule is an error, not a warning, so design for
  it instead of discovering it at the lint gate.
- **The tab icon is browser chrome, so it needs per-scheme artwork, not CSS.** Four assets in
  `public/`: `favicon.svg` (adaptive default; media query kept for no-JS/reader contexts),
  `favicon-dark.svg`, `favicon.ico` and `favicon-dark.ico`. Both `<link rel="icon">` entries in
  `app/root.tsx` carry `data-light`/`data-dark` and `SYSTEM_THEME_SCRIPT` — which already sets
  `data-mode` before paint — re-points them, so that `<script>` must stay AFTER the links in
  `<head>`: an inline head script runs at parse time and finds no links if it precedes them.
  The links carry `suppressHydrationWarning`. Dark fills come from Kumo's paired tokens
  (`--text-color-kumo-default` is `#f5f5f5` in dark), never an invented grey. Why a media query
  inside the SVG cannot do this job: `references/theme-adaptive-assets.md`.
- **Prove appearance changes through the path the user sees, not a proxy.** Nothing in the gate
  covers how an asset or page looks, and `chromium` is on PATH inside the sandbox: `node
  scripts/cdp-scheme-shot.mjs <url> light|dark <out.png>` screenshots through CDP with an
  emulated colour scheme. That proves the FILE renders; it does not prove the browser uses it
  where the user is looking. For browser-chrome assets (favicons) read the `--log-net-log` of
  which favicon URL was actually fetched and window-render the tab strip — the generic rules and
  harness are the `browser-chrome-assets` skill. Assert with pixels, comparing luminance bands
  against the local background rather than exact fills at icon sizes, and treat a vision model's
  prose as a sanity check on top, never the measurement.
- **Running the app for a UI probe.** `npm run dev` wants Cloudflare credentials for its remote
  bindings (`AI` is remote in dev, `send_email` is `remote: true`), which the sandbox lacks:
  temporarily make those bindings local (or point the plugin at `wrangler.test.jsonc`), start it
  with `CHOKIDAR_USEPOLLING=1` (Vite's watcher otherwise dies with `ENOSPC`), and
  `git checkout -- wrangler.jsonc` before committing. It binds `localhost`, so curl
  `http://localhost:5173/`; the SSR head it returns is the artifact to assert on — the vitest
  pool cannot produce it (`virtual:react-router/server-build` does not resolve there), so
  `tests/*.test.ts` stays for API/DO behaviour.
- Read the newest `.hermes/plans/*feature-gap-analysis*` file before proposing features — it
  tracks what is implemented, what is deferred, and why (including the outbound-fetch items
  that need an SSRF policy first). Then re-verify it against HEAD before repeating anything:
  waves land here in hours, so `git log --oneline <plan-commit>..HEAD | wc -l` first and
  re-grep every "absent" claim you intend to reuse.
- Survey surfaces by grep, not by reading whole files: agent tools are
  `grep -nE ': defineTool' workers/agent/index.ts`, MCP tools
  `grep -nA3 'this.server.tool(' workers/mcp/index.ts` — the drift between the two lists is
  itself a finding. Demand signals: the upstream issue tracker
  (`api.github.com/repos/cloudflare/agentic-inbox/issues?state=open`; unauthenticated is fine).
  Check `git log HEAD..upstream/main` first — when upstream has not moved, issues carry the
  demand, not upstream commits.

## Reporting to this operator

- When he proposes a feature, answer in a line or two — yes/no, what it needs, the one gotcha
  — and dispatch the work. A feasibility question does not want a ranked survey of
  alternatives; long hedged answers get interrupted.
- Separate what you VERIFIED (command + observed result) from what a subagent reported. He
  audits claims: state the observation time and re-probe live state before calling anything
  currently true.
- Keep unrequested work off the remote: merge to local `main`, never push.
- A UI/visual claim ships only with an observation from the path he uses: real browser, real colour scheme, and what the browser actually fetched and
  rendered. A component test, an `<img>` render or an emulated media query is a proxy — reporting
  one as verification is what produces a follow-up "it doesn't work".
- He gates a wave on the previous one being deployed. After a batch lands, hand over the
  deploy command plus a per-feature smoke checklist and stop there — do not start the next
  batch, even if he already named its order, until the deploy is confirmed. Confirmation can
  be evidence-based: when the deploy timeline and live-bundle markers show the wave is out,
  say so with the observation time, record the verified status in the wave log's deploy line,
  and move on — do not re-ask.
- Between waves, "what should we work on?" is a planning question, not a feature review: do
  the reconnaissance first (recent sessions, the wave log, live deploy state), then answer
  with the verified state plus a short numbered menu of the roadmap remainder — the wave
  doc's §3 numbers, effort sizes, one marked recommendation — so he orders the queue like
  last time. Dispatch nothing until he orders it.

## Support files

- `references/architecture-map.md` — subsystem index.
- `references/theme-adaptive-assets.md` — favicon wiring (four assets, `data-light`/`data-dark`
  links, script order), why an in-SVG media query cannot carry the tab icon, `.ico` frame
  generation, and the measured expectations to reproduce.
- `scripts/cdp-scheme-shot.mjs` — screenshot a URL through CDP with an emulated
  `prefers-color-scheme`; prints the resolved page scheme so you know the emulation applied.
