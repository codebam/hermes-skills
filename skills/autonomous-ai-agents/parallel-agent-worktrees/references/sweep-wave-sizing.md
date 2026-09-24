# Sizing a sweep wave (lint / typecheck error inventories)

A sweep wave is a batch of children whose job is to fix an existing backlog of errors — lint
violations, typecheck errors — rather than to build a feature. It is sized from data, never
guessed, and the numbers go in the briefs instead of the error list.

## Produce the inventory first, machine-readable

```bash
npx eslint <paths> -f json > /tmp/lint.json     # per-file message arrays
npx tsc -b --pretty false 2>&1 | grep 'error TS' # or the repo's typecheck script
```

For a type-aware config, one file can carry hundreds of errors from a single rule; a `tsc` run
may need a strictness flag forced on to surface the class you are sweeping (a small helper that
runs `tsc` with one flag forced and joins each error to its real source line beats eyeballing
the default output).

## Tally, then partition

Tally per file and per rule, then partition by that tally:

- **One writer per file.** Rule 6 of the skill is the reason: two children in one file is the
  only thing git cannot merge.
- **A file with a three-digit error count gets its own child.** Splitting it across two children
  guarantees a conflict in the same regions.
- **Group the small files** so each child has a coherent slice (a directory, a subsystem) rather
  than an arbitrary count.
- **Expect the fix to be mechanical** — casts, annotations, rule-specific rewrites — which is why
  the inventory, not judgement, is what the sizing needs.

## What goes in the brief

Never the raw error list: it is huge, it changes as siblings commit, and a child that reads it
instead of regenerating it works from stale line numbers. Give each child:

1. the count it owns, broken down by rule;
2. the command that regenerates exactly its slice;
3. the file list it owns and the files that are off-limits;
4. the gate command scoped to its own paths (`npx eslint <paths> --max-warnings 0`), since a
   repo-wide lint in a parallel wave lints every sibling's half-finished branch.

A sweep child's "done" is its slice regenerating to zero errors — not the repo-wide command
being green, which only the parent can assert after every branch is merged.
