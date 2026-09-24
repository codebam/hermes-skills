---
name: typescript-strictness-migration
description: Use when tightening TS strictness or adopting ESLint rules.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [typescript, compiler-flags, strictness, migration, verification]
    related_skills: [parallel-agent-worktrees, requesting-code-review]
---

# TypeScript Strictness Migration

Enable stricter compiler flags in an existing codebase without changing runtime behaviour:
audit which flags the code can adopt, fix the errors flag by flag, enable centrally, verify
with probes plus the full gate. When the fix volume is large, hand the fixing to parallel
worktree agents (`parallel-agent-worktrees`); this skill covers the audit, the fix patterns,
and the verification. The same procedure covers adopting type-aware ESLint in a repo that has
no lint config yet — measure the inventory, land the config and scripts centrally, sweep the
errors by file ownership, verify the combination.

## When to Use

- Enabling stricter compiler flags (`noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`,
  `verbatimModuleSyntax`, ...) in an existing TS project or workspace.
- Adopting ESLint — especially a type-aware `@typescript-eslint` config — where no lint config
  exists yet, or where an existing config produces a large error inventory.
- Any sweep of pre-existing static-analysis errors whose fix volume justifies parallel
  worktree agents.

## Candidate flags

`strict: true` already covers `noImplicitAny`, `strictNullChecks`, `strictFunctionTypes`,
`strictPropertyInitialization`, `useUnknownInCatchVariables`, `strictBuiltinIteratorReturn`
and friends — probing those is wasted work. The flags that add enforcement on top:

| flag | catches |
|---|---|
| `noUncheckedIndexedAccess` | every `arr[i]` / `record[key]` becomes `T \| undefined` |
| `exactOptionalPropertyTypes` | explicit `undefined` is not assignable to `prop?: T` |
| `noPropertyAccessFromIndexSignature` | `obj.prop` on an index-signature type (bracket access required) |
| `noImplicitOverride` | overrides missing the `override` modifier |
| `noImplicitReturns` | functions with a path that falls off the end |
| `noFallthroughCasesInSwitch` | unannotated switch fallthrough |
| `verbatimModuleSyntax` | value-position imports of types (needs `import type` / inline `type`) |
| `noUncheckedSideEffectImports` | bare `import 'x'` that resolves to nothing |
| `isolatedModules` | constructs single-file transpilers cannot handle |

Notes: `allowUnreachableCode: false` and `allowUnusedLabels: false` are already the compiler
defaults — setting them explicitly is a no-op, not a win. `erasableSyntaxOnly` is a syntax
restriction (enums, namespaces, parameter properties) for type-stripping runtimes, not a
type-safety flag.

## Procedure

1. **Probe every workspace x flag and count errors before deciding anything.**
   - tsc: `npx tsc -p <workspace>/tsconfig.json --noEmit --<flag> 2>&1 | grep -cE 'error TS'`
     (CLI flags override the tsconfig; `--allowUnreachableCode false` works the same way).
   - Checkers without CLI overrides (svelte-check): write a throwaway `tsconfig.probe.json`
     next to the real config —
     `{"extends": "./tsconfig.json", "compilerOptions": {"<flag>": true}}` — run
     `npx svelte-check --tsconfig ./tsconfig.probe.json` and parse the summary line
     (`found N errors`). Do NOT count machine-format lines by prefix: the format varies and a
     wrong grep silently reports 0, which reads as "already clean".
   - Record a per-file breakdown for the files with errors; that drives the partitioning.
2. **Zero-error flags are free.** Enable them as config-only changes; they need no fixes.
3. **Fix, partitioned by file ownership.** Flags are per-PROGRAM: a flag enabled in a
   package's tsconfig does not apply when another project compiles that package's source, and
   a workspace-linked shared source file is typechecked under every consumer's flags — its
   errors show up in all of their counts. Fix such cross-cutting files on the main branch
   before branching, or every parallel worker collides on them — and when the cross-cutting
   file is itself part of the sweep, give it a single writer of its own and declare it
   off-limits in every other brief.
4. **Enable centrally, verify with the combination.** Do not have each parallel branch edit
   the tsconfig: N branches editing one small config file is an N-way conflict. Enable all
   flags in one commit after the fixes land, then run the full gate (per-workspace typecheck,
   build, tests, lint) with everything on — a per-flag probe is isolation, and the combination
   is what ships.
5. **Attribute leftovers by re-probing.** With all flags on, a fresh error count says how many
   are left; per-flag probes say which flag owns them.

## Fix rules

- Preserve runtime behaviour exactly. These flags expose latent `undefined`s; the fix is a
  guard that makes the existing behaviour explicit, not a new default that changes what the
  program does when the value is absent.
- Prefer explicit guards, `??` defaults, and optional chaining over non-null `!` assertions
  and `as` casts — assertions satisfy the flag while defeating its purpose, and project rules
  commonly ban them outright.
- Never change public signatures, exported types, or wire formats to make a flag happy.
- Per-error-code patterns: `references/fix-patterns-by-error-code.md`.

## Adopting type-aware ESLint

A lint sweep is a strictness migration with a different error taxonomy: land the config and
scripts centrally, sweep the errors by file ownership, verify the combination. Rules that cost
time when missed:

- **Land the config, scripts and devDeps on `main` before branching.** The config is the gate
  the children run; a branch without it can verify nothing. Add the linter to each workspace
  member's `package.json` and reconcile with ONE `npm install` at the workspace root — never
  inside a member, which materialises a member-local `node_modules` and splits resolution.
- **`projectService: true` plus `tsconfigRootDir: import.meta.dirname`** is what makes
  type-aware linting work from a worktree as well as the main checkout; without the explicit
  root the parser resolves the project relative to the CWD and the type-aware rules quietly
  stop firing.
- **Measure before partitioning** with `eslint <paths> -f json` tallied per file and per rule.
  `no-unsafe-*` errors are downstream of `any`: one `any` fix clears a whole cluster, so brief
  children to fix root causes and re-run the tally rather than chase line numbers.
- **Police silencing.** Ban `eslint-disable`, `@ts-ignore`, `@ts-expect-error` and `as any` in
  every brief, then grep the merged diff for them before believing a green run.
- Config shape, rule triage and the exact commands: `references/eslint-adoption.md`.

## Pitfalls

- **The compiler is the authority on positions.** When a line-numbered file view disagrees
  with the compiler's reported line, trust the compiler; inspect with `awk 'NR>=X && NR<=Y'`.
- **A probe tsconfig is a build artifact.** Delete it before committing; it must never ride
  into a merge or a review.
- **Don't fix other flags' errors while fixing yours.** In a partitioned wave every error
  outside your inventory belongs to a sibling — editing it collides at merge time.
- **Verify the enabled state, not just the probes.** After enabling flags, re-run the whole
  gate on the integration branch; a combination can fail where each flag alone was green.
