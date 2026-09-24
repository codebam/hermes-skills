---
name: cloudflare-workers-testing
description: Use when testing, deploying, or verifying Cloudflare Workers and Durable Objects.
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
- **Assert whether a Durable Object was touched at all, not only what is inside it.**
  `listDurableObjectIds(env.<BINDING>)` (from `cloudflare:test`) lists the instances that
  exist without instantiating one — the only way to prove a negative, e.g. that a setting kept
  the DO out of the request path entirely. Always pair it with a positive control in the same
  file (same delivery, one setting flipped) so a green test cannot come from the trigger being
  broken rather than gated. Background work scheduled through `ctx.waitUntil` needs
  `createExecutionContext()` to capture it and `await waitOnExecutionContext(ctx)` to settle it
  before the assertion, or the fetch has not landed yet.
- **DO alarms are testable — drive them, never sleep.** `runDurableObjectAlarm(stub)` runs the
  alarm handler on demand, and `runInDurableObject(stub, (_, state) => state.storage.getAlarm())`
  reads the armed time, so one test asserts both the schedule and the effect (an alarm set in
  the past fires by itself, no waiting). A fired alarm does not reschedule itself, so the handler
  must re-arm — assert the re-armed time, and run the handler twice to prove idempotence. That
  self-firing is also a determinism trap: a test that must prove nothing fired YET schedules in
  the future and forces the row due with raw SQL, because a row written with a due time of `now`
  can be drained by the runtime before the assertion runs — and when the code under test is what
  arms an immediate alarm (a retry that re-arms at `now`), poll the resulting state with
  `vi.waitFor` instead of asserting once.
- **An outbound fetch needs an injected implementation to be testable.** This pool ships no
  `fetchMock` (check `node_modules/@cloudflare/vitest-pool-workers` before reaching for one) and
  the suite must not touch the network, so the outbound call takes a `fetchImpl` parameter
  defaulting to the global `fetch`, and the test asserts method, headers and body against a stub.
  To cover the ROUTE rather than only the module, `vi.stubGlobal("fetch", …)` plus
  `vi.unstubAllGlobals()` in cleanup does capture the Worker's own outbound calls in this pool
  (same-isolate stubbing), so the end-to-end path — click handler's endpoint, guard, request
  shape — can be asserted instead of faked: use the injected implementation when the stub has
  to survive isolation, the global stub when you want the request the route really makes.
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
- **Probe a runtime capability with a throwaway spec before designing around it.** Whether an
  SQL feature, a tokenizer or a binding shape exists in THIS runtime is not something a plan
  document or an older runtime answers: write one scratch spec under `tests/` (the pool's
  include glob collects it), exercise the feature through `runInDurableObject` (DDL, writes,
  reads), read the answers, then delete the file. Surface the results by THROWING an `Error`
  whose message carries `JSON.stringify(result)` — a failure message always reaches the
  `vitest run` log, while console output from inside the pool worker may not. Give each
  statement its own try/catch so one rejection (workerd's authorizer blocks some SQLite
  functions, e.g. `sqlite_version()`) does not hide the rest of the answers. Measured DO
  SQLite full-text capabilities and the exact FTS5 recipe: `references/do-sqlite-fts5.md`.
- **Prefix/substring search in DO SQL: use `substr(LOWER(col),1,length(?)) = ?`, not `LIKE`.**
  `LIKE` treats `%` and `_` in user input as wildcards and DO SQLite restricts pattern shapes;
  the `substr` form is exact, keeps operator input literal, and the same expression serves a
  matching `count(*)` beside the paged select (a bare `count(*)` with the select's own LIMIT
  removed gives a `totalCount` the page can trust).
- **Gate order for a Workers change**: regenerate binding types (`wrangler types`) → `tsc -b`
  (or the repo's typecheck script) → `vitest run` → the app build. Run the build once on the
  integration branch, not inside every parallel editing session.
- **Decide whether the test tree is inside the typecheck project.** `tsc -b` only checks the
  files its project references include; when `tests/` is not listed, vitest transpiles without
  typechecking and test-side type errors surface only at runtime. Add the tree to a tsconfig or
  accept the gap deliberately.
- **Assert rejected requests through the route, not through the RPC rejection.** A Durable
  Object method that throws is reported by the pool a second time as an unhandled rejection,
  so `vitest run` exits non-zero even when every test passed (a synchronous throw does not
  reproduce it, and `runInDurableObject` reproduces it too, so it is not a call-style choice).
  Drive the request with `SELF` from `cloudflare:test` and assert the status and error message
  the route returns — that is the contract clients depend on. Do NOT reach for
  `dangerouslyIgnoreUnhandledErrors`: it hides genuine unhandled rejections for the rest of
  the suite. Details: `references/durable-object-rpc-contracts.md`.
- **Errors crossing the DO RPC boundary lose their class.** A thrown subclass arrives at the
  caller as a rebuilt `Error` whose `name` is generic and whose message carries the original
  class name as a prefix (`RuleValidationError: Unknown folder: ...`), so an
  `instanceof`/`name` guard falls through and the route answers 500 instead of the intended
  400. Match the message prefix as well, and validate at the edge with a helper shared with
  the DO so bad input never becomes an RPC round-trip.

## Pitfalls

- **Pool fails to start: check the bundled runtime before your config.** The pool drives the
  `workerd` binary shipped with wrangler; if install scripts were skipped during `npm install`
  the binary is unusable and every test dies at startup. Verify with
  `node_modules/@cloudflare/workerd-linux-64/bin/workerd --version`, then re-run the install
  scripts (`npm rebuild`) instead of debugging your config.
- Resolving `@cloudflare/vitest-pool-workers/config` throws "Missing './config' specifier"
  on 0.22+ — that means you are on the plugin API, not that the install is broken.
- `Sourcemap for ... points to missing source files` lines during a run are noise; the
  pass/fail summary is what matters. Same for `Binding AI needs to be run remotely` uncaught
  exceptions when the test config carries a model binding and some code path reaches it — keep
  model calls out of tests by turning the feature off through settings data, and read the
  summary rather than the log.
- Tests asserting on SSR/HTML output are brittle in this pool; assert on the API response
  and the storage row instead.
- A DO test that mutates storage in one test can leak into the next — use a fresh mailbox
  name / instance id per test rather than resetting shared state.

## Support files

- `templates/vitest.config.ts` — known-good pool config (plugin API, offline-safe).
- `templates/wrangler.test.jsonc` — slim test-only Worker config (no routes, no send binding).
- `references/durable-object-rpc-contracts.md` — how DO RPC reports rejections, what error
  identity survives the boundary, how to assert route contracts from tests, and the
  `agents`-framework `destroy()` quirk.
- `references/tool-surface-contracts.md` — pinning an app's agent and MCP tool lists as tests
  (live `/mcp` handshake, exported tool factory).
- `references/do-sqlite-fts5.md` — what DO SQLite's FTS5 actually supports (external-content
  tables, `rebuild`, column-scoped sync triggers, trigram tokenizer), its measured matching
  behaviour for quoted terms and short terms, the escaping rules operator input needs, and the
  throwaway-spec probe recipe for feature-detecting the runtime.
- `references/deploy-and-migrations.md` — what has to run after `wrangler deploy` (usually
  nothing), the two migration layers, what a live URL can and cannot prove, and how to prove
  which features a live build actually contains (deployments timeline + live-bundle fetch).
- `scripts/live-worker-markers.py` — fetch a deployed worker's live bundle through the
  Cloudflare API and count feature markers; the evidence step before reporting a build as live.
