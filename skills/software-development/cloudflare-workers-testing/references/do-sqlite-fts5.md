# FTS5 in Durable Object SQLite

Capability evidence for workerd's DO SQLite (the runtime `@cloudflare/vitest-pool-workers`
drives), measured by probe rather than assumed from docs. Re-probe if the runtime changes.

## What works

- `CREATE VIRTUAL TABLE <name> USING fts5(...)` — plain tables, `snippet()`, `bm25()`,
  `MATCH` and `NEAR(...)` all parse and run.
- **External-content tables** — the shape a search feature wants, so the index does not
  duplicate message bodies:

  ```sql
  CREATE VIRTUAL TABLE emails_fts USING fts5(
      subject, body, sender, recipient, cc, bcc,
      content='emails', content_rowid='rowid', tokenize='trigram'
  );
  INSERT INTO emails_fts(emails_fts) VALUES('rebuild');   -- backfill existing rows
  ```

  The base table needs a `rowid` (the default; only `WITHOUT ROWID` tables lack one). Queries
  join `base.rowid = <fts>.rowid`.
- **Sync triggers** — AFTER INSERT (`INSERT INTO fts(rowid, cols) VALUES (new.rowid, new.cols)`),
  AFTER DELETE (the `'delete'` command form carrying OLD values), and
  `AFTER UPDATE OF col1, col2 ON base` (delete OLD + insert NEW). Column-scoped UPDATE triggers
  work, so flag-only updates (`read`, `starred`) do not churn the index.
- **`tokenize='trigram'`** — substring matching, the closest thing to `LIKE '%term%'` at index
  speed: no dictionary needed and CJK works; the index is larger.

## Measured matching behaviour (trigram)

| Input | Result |
|---|---|
| `"arter"` against "quarterly" | matches (mid-word substring) |
| multiple quoted terms | match; adjacent terms AND |
| `"100%"`, `"_literal_"` | match literally — `%`/`_` need no escaping inside a quoted phrase |
| CJK substring | matches |
| `"QUARTERLY"` | matches (case-insensitive by default) |
| terms shorter than 3 chars | ZERO rows, no error — route them to a `LIKE` fallback |
| a 120-char term | matches exactly; a near-miss returns nothing |
| `"say ""hi"" now"` | matches text containing `say "hi" now` — double a `"` INSIDE the phrase to escape it |
| raw `(`, `*`, `-`, unbalanced `"` | ERROR — every operator-supplied term must be quoted/escaped before `MATCH` |

So the input pipeline is: split on whitespace; terms of length >= 3 become a quoted, escaped
FTS phrase; shorter terms go through the existing `LIKE` path and the two sets are ANDed.
Never interpolate operator text into `MATCH` unquoted. The statement's bound-parameter count is
limited in this runtime, so the pipeline caps how many terms one query may carry (the app caps
at 32) instead of passing unbounded operator input into the statement.

## Not available

- `sqlite_version()` is refused by workerd's authorizer (`not authorized to use function`).
  Feature-detect by trying the real statement, not by asking the version.

## The probe recipe

Scratch spec under `tests/` so the pool's include glob collects it; delete it afterwards — a
probe file that stays behind rides into the merge, and a failing probe breaks the suite.

```ts
import { env, runInDurableObject } from "cloudflare:test";
import { it } from "vitest";

it("probes a runtime capability", async () => {
  const stub = env.MAILBOX.get(env.MAILBOX.idFromName("probe@example.com"));
  const out = await runInDurableObject(stub, (_i, state) => {
    const sql = state.storage.sql;
    const result: Record<string, string> = {};
    const attempt = (label: string, fn: () => unknown) => {
      try { result[label] = `ok ${JSON.stringify(fn())}`; }
      catch (e) { result[label] = `error: ${(e as Error).message}`; }
    };
    attempt("create", () => { sql.exec("CREATE VIRTUAL TABLE t USING fts5(a)"); return "created"; });
    attempt("match", () => [...sql.exec("SELECT rowid FROM t WHERE t MATCH ?1", '"x"')].length);
    return result;
  });
  throw new Error("PROBE RESULTS: " + JSON.stringify(out, null, 2));
});
```

Notes that cost time when missing:
- The thrown `Error` IS the output channel: a failure message always reaches the `vitest run`
  log, while console output from inside the pool worker may not.
- One try/catch per statement — a single rejected statement otherwise truncates the report at
  it (workerd's authorizer blocks some functions).
- `state.storage.transactionSync(() => {...})` wraps multi-statement setup when the probe must
  mirror what a migration runner does.
- Probe on a throwaway mailbox id, and read the results before designing anything: a plan
  document asserting a runtime capability is not evidence.
