# Architecture Map

Subsystem → files index. Verify with grep before trusting a path — this is a map, not a
contract.

## Worker (API)

- `workers/app.ts` — entry: fetch handler, Cloudflare Access JWT verification, MCP mount at
  `/mcp`, DO class re-exports, `scheduled()` cron adapter (daily sweep: retention + image-proxy
  cache).
- `workers/index.ts` — Hono routes (mailboxes, email CRUD/move/restore, bulk actions, drafts,
  send/reply/forward, per-mailbox and cross-mailbox search, rules + preview + retroactive apply,
  templates, settings, models, webhook test, one-click unsubscribe, image proxy) plus
  `receiveEmail` (inbound: PostalMime parse → sender policy → rules → Jev classification →
  storage → auto-draft trigger).
- `workers/lib/` — `tools.ts` (agent + MCP tool implementations), `ai.ts` (`verifyDraft`, model
  resolution), `categorize.ts` (Jev), `rules.ts` (rule engine), `rule-outbound.ts` (rule-driven
  forwards/auto-replies and their Sent copy), `schemas.ts` (zod for every route),
  `email-helpers.ts` (`listMailboxes`, ids, threading), `attachments.ts` (R2 store), `mailbox.ts`
  (settings defaults, `MailboxContext`), `search-all.ts`, `like-terms.ts` + `fts-terms.ts` (the
  search term pipeline), `trash-retention.ts`, `contacts.ts`, `sender-policy.ts`,
  `agent-actions.ts` (`runAudited`), `ssrf-guard.ts` (the single outbound guard: unsubscribe and
  image-proxy modes), `image-proxy.ts` (same-origin image fetch + R2 cache), `templates.ts`.
- `workers/durableObject/` — `MailboxDO`: SQLite schema in `migrations.ts` (append-only),
  email/folder/rule/sender-policy methods, search SQL (FTS5 `emails_fts`, migration 23),
  templates storage (migration 24), trash/restore/purge, send rate limit, alarm arm/drain.
- `workers/agent/` — per-mailbox and all-mailbox chat, auto-draft. `workers/mcp/` — the
  agent-facing MCP server. `workers/email-sender.ts` — outbound send via the `send_email`
  binding. `workers/db/schema.ts` — drizzle definitions mirroring every migration.

## UI (React Router 7)

- `app/routes/` — `mailbox.tsx` (shell), `email-list.tsx` (list, toolbar, Empty trash),
  `all-accounts.tsx`, `all-search.tsx` + `search-results.tsx`, `settings.tsx` (mailbox),
  `global-settings.tsx`, `rules.tsx` (preview + Apply-to-existing progress).
- `app/components/` — `EmailPanel.tsx` (message view), `EmailIframe.tsx` (sandboxed body +
  CSP), `MessageBody.tsx` (remote-image rewriting), `TemplatePicker.tsx` (composer templates),
  `email-panel/RemoteImagesNotice.tsx`, `BulkActionBar.tsx`, `Sidebar.tsx`, `Header.tsx`,
  `AiModelsCard.tsx`, composer components.
- `app/queries/` + `app/services/api.ts` — react-query hooks and fetch wrappers (cache keys in
  `app/queries/keys.ts`; hook files include `rules.ts` and `templates.ts`). `app/hooks/` —
  `useComposeForm.ts`, `useEmailSelection.ts`, `useRemoteImages.ts`.

## Data

- Per mailbox: Durable Object SQLite (`folders`, `emails`, `emails_fts`, `attachments`, `rules`,
  `rule_stats`, `templates`, `contacts`, `agent_actions`, `sender_policy`, plus the
  `d1_migrations` bookkeeping table).
- R2: `attachments/{email_id}/{att_id}/{filename}`, `image-proxy/<sha256-of-url>` cache, and
  `mailboxes/<address>.json` settings records (the mailbox list is derived by listing that
  prefix).

## Tests

- `tests/*.test.ts` on vitest + `@cloudflare/vitest-pool-workers` (`vitest.config.ts`,
  `wrangler.test.jsonc`, `remoteBindings: false`). Route contracts via `SELF.fetch`, DO internals
  via `runInDurableObject`, one mailbox per test. Harness details: `cloudflare-workers-testing`.
