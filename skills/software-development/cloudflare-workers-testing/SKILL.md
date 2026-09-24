---
name: cloudflare-workers-testing
description: Use when testing Cloudflare Workers or Durable Objects.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [cloudflare, workers, durable-objects, vitest, testing, verification]
    related_skills: [test-driven-development, parallel-agent-worktrees]
---

# Cloudflare Workers Testing

Unit tests that mock the platform prove almost nothing in a Workers app: the bugs live in
Durable Object SQL, storage migrations, and route wiring. Run the tests inside workerd with
`@cloudflare/vitest-pool-workers` so DO storage, R2 and the Hono/vite worker are real.

## Setup

1. Install the pair — the pool pins the runner:
   `npm i -D vitest@^4 @cloudflare/vitest-pool-workers`
   (pool-workers 0.22+ peer-requires vitest ^4.1; installing vitest 3 first fails with an
   ERESOLVE conflict, so install both in one command and let npm resolve.)
2. `templates/vitest.config.ts` — in 0.22+ the pool is configured as a **Vite plugin**:
   `cloudflareTest({ wrangler: { configPath }, remoteBindings: false })`. The old
   `defineWorkersConfig()` helper from `@cloudflare/vitest-pool-workers/config` no longer
   exists; `@cloudflare/vitest-pool-workers/codemods/vitest-v3-to-v4` documents the new shape.
3. `templates/wrangler.test.jsonc` — a slim copy of the real Worker config: same
   compatibility date/flags, same DO bindings and migrations, but no custom routes and no
   outbound send binding, so a test run can never deliver mail or reach the network.
4. Add a `test` script (`vitest run`) plus one smoke test that boots a Durable Object and
   reads its schema back. The smoke test is what proves the harness before anyone writes
   real tests against it.

## Rules

- **`remoteBindings: false` is required for offline runs.** Otherwise the pool opens a remote
  proxy session and fails asking for `CLOUDFLARE_API_TOKEN`, even for purely local tests.
- **Read state with `cloudflare:test`, address the app with `cloudflare:workers`.**
  `runInDurableObject(stub, (instance, state) => ...)` runs code inside the DO (seed rows,
  inspect `state.storage.sql`); calling public methods on `env.<BINDING>.get(...)` stubs
  exercises the real RPC path the app uses.
- **Mirror every binding and DO class into both configs.** A binding added only to the
  production config makes tests fail in a way that looks like a code bug.
- **Keep the suite deterministic and local**: no network, no model calls, no mail. If a test
  needs a provisioned resource (vector index, queue consumer, live API), it does not belong
  in this suite — assert at the seam instead and say so.
- **Migrations are append-only.** Add a new entry per schema change; never edit an applied
  one. Durable Object SQL has no `BEGIN`/`COMMIT` — wrap multi-statement migrations in
  `state.storage.transactionSync(...)`.
- **Annotate rows from `state.storage.sql.exec`.** The result is untyped, so TypeScript infers
  a shape from the first call site and later property accesses fail to compile — declare the
  row interface beside the query and map into it.
- **Gate order for a Workers change**: regenerate binding types (`wrangler types`) → `tsc -b`
  (or the repo's typecheck script) → `vitest run` → the app build. Run the build once on the
  integration branch, not inside every parallel editing session.
- **Decide whether the test tree is inside the typecheck project.** `tsc -b` only checks the
  files its project references include; when `tests/` is not listed, vitest transpiles without
  typechecking and test-side type errors surface only at runtime. Add the tree to a tsconfig or
  accept the gap deliberately.

## Pitfalls

- **Pool fails to start: check the bundled runtime before your config.** The pool drives the
  `workerd` binary shipped with wrangler; if install scripts were skipped during `npm install`
  the binary is unusable and every test dies at startup. Verify with
  `node_modules/@cloudflare/workerd-linux-64/bin/workerd --version`, then re-run the install
  scripts (`npm rebuild`) instead of debugging your config.
- Resolving `@cloudflare/vitest-pool-workers/config` throws "Missing './config' specifier"
  on 0.22+ — that means you are on the plugin API, not that the install is broken.
- `Sourcemap for ... points to missing source files` lines during a run are noise; the
  pass/fail summary is what matters.
- Tests asserting on SSR/HTML output are brittle in this pool; assert on the API response
  and the storage row instead.
- A DO test that mutates storage in one test can leak into the next — use a fresh mailbox
  name / instance id per test rather than resetting shared state.

## Support files

- `templates/vitest.config.ts` — known-good pool config (plugin API, offline-safe).
- `templates/wrangler.test.jsonc` — slim test-only Worker config (no routes, no send binding).
