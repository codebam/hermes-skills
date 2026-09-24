# Fix patterns by error code

The compiler's own message usually names the fix ("Consider adding 'undefined' to the type of
the target", "must be accessed with ['key']"). Use it. These are the recurring shapes.

## noUncheckedIndexedAccess

- **TS18048 / TS2532** (`'x' is possibly 'undefined'`, `Object is possibly 'undefined'`) — an
  indexed read yields `T | undefined`.
  - Loop bodies: `const item = items[i]; if (!item) continue;` — one guard line, behaviour
    unchanged for dense arrays.
  - One-shot reads: `const x = arr[i] ?? fallback;` when the fallback is semantically identical
    to what the absent case already produced.
  - Method chains: `obj[key]?.trim()` when absence is naturally handled downstream.
- **TS2345 / TS2322** (argument / assignment not assignable) — the undefined travels into a
  call or assignment. Guard before the call rather than asserting at it; for `Number(x)` /
  `parseInt(x)` arguments, guard or default first.
- Prefer `for (const item of items)` over index loops when the index is not otherwise used —
  it removes the class of error instead of patching it.

## exactOptionalPropertyTypes

- **TS2375 / TS2379** (`{ prop: T | undefined }` not assignable to `{ prop?: T }`) — the caller
  passes an explicit `undefined` into an optional property.
  - Omit when undefined: `...(value === undefined ? {} : { prop: value })` — this matches the
    runtime meaning of "absent" and is the safest default for API payloads.
  - Do not default to `?? ''` / `?? 0` for API fields: an empty string is a different wire
    value from an omitted field.
- **TS2412** (`T | undefined` assigned to a property declared `T`) — guard the assignment;
  widen the declaration to `prop?: T` only when the value is genuinely optional at runtime,
  and keep the change local.
- **TS2769** (overload mismatch) is often a downstream symptom — fix the undefined at its
  source first, then re-probe.

## The one-liners

- **TS4111** (`noPropertyAccessFromIndexSignature`) — bracket access `obj['key']` at the exact
  site the compiler flags. Pure syntax change; do not restructure the payload.
- **TS4114** (`noImplicitOverride`) — add the `override` modifier to the overriding member.
- **TS7030** (`noImplicitReturns`) — inspect what the other paths return and make the remaining
  path match; in framework callbacks (e.g. Svelte `$effect`) do not invent a cleanup return
  that did not exist — an explicit bare `return;` is usually the fix.
- **TS1484** (`verbatimModuleSyntax`) — inline `type` modifier in the existing import
  (`import { A, type B } from '...'`): a one-line change, no import reordering.

## Partitioning note

When several flags touch one file, extract each flag's error line numbers first and compare
sets: fixes on disjoint lines auto-merge, adjacent-line collisions do not. Fix the flag with
the largest overlap first and re-probe — later counts are computed on the already-fixed file.
