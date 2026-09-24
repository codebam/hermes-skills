# Adopting type-aware ESLint in a TS monorepo

For a repo that has no lint config yet (or has it in only one workspace member) and a large
error inventory to clear. The sweep is delegated to worktree children
(`parallel-agent-worktrees`); this file holds the config, the wiring, the inventory commands
and the rule triage.

## 1. Config: flat config, type-aware, one per package

One `eslint.config.js` per workspace member, copied and adapted (this matches the convention
where the frontend member already ships one):

```js
import prettier from 'eslint-config-prettier';
import path from 'node:path';
import { includeIgnoreFile } from '@eslint/compat';
import js from '@eslint/js';
import { defineConfig } from 'eslint/config';
import globals from 'globals';
import ts from 'typescript-eslint';

const gitignorePath = path.resolve(import.meta.dirname, '.gitignore');

export default defineConfig(
	{ ignores: ['eslint.config.js', 'worker-configuration.d.ts'] }, // the config is not in the TS project; generated binding types are not linted
	includeIgnoreFile(gitignorePath),           // picks up .worktrees/, dist/, .svelte-kit/, ...
	js.configs.recommended,
	ts.configs.recommendedTypeChecked,
	prettier,                                   // keep LAST among the shared configs
	{
		languageOptions: {
			globals: { ...globals.worker, ...globals.node },
			parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname }
		},
		rules: {
			'no-undef': 'off', // typescript-eslint: the compiler owns undefined identifiers
			'@typescript-eslint/no-explicit-any': 'error',
			'@typescript-eslint/no-unused-vars': ['error', { varsIgnorePattern: '^_', argsIgnorePattern: '^_' }],
			'@typescript-eslint/consistent-type-imports': ['error', { prefer: 'type-imports' }]
		}
	}
);
```

- `includeIgnoreFile(<the repo's .gitignore>)` is what keeps `.worktrees/` out of the run; if
the worktree directory is not gitignored, the run reports every sibling's copy of the tree.
- Ignore generated declaration files explicitly (`worker-configuration.d.ts` and friends) —
they flood the report with hundreds of unrelated errors.
- **Ignore the config file itself.** With `projectService: true`, `eslint .` also lints
`eslint.config.js`, which no tsconfig includes, and fails with `Parsing error: ... was not
found by the project service` — which reads like a broken install and is not. Put the config
file in `ignores` (or in `allowDefaultProject`); the per-file runs never hit it, so the bug
only appears on the first whole-directory run.
- `recommendedTypeChecked` is the type-aware tier and the reason the inventory is large; the
non-type-checked `recommended` reports a small fraction of it, so choosing it silently halves
the work and the value.
- A shared package consumed as source (`exports: "./src/index.ts"`) uses the same config, with
its own gitignore path resolved from its directory and the matching `globals.*` set.

## 2. Workspace wiring

- Each member: `"lint": "eslint ."` and `"lint:fix": "eslint . --fix"`.
- Root: `"lint": "npm run lint --workspaces --if-present"` (plus the `:fix` twin), so CI and
the Makefile cover every member without a per-member list.
- CI: replace any single-member lint step with one `npm run lint`.
- Deps per member: `eslint`, `@eslint/js`, `@eslint/compat`, `typescript-eslint`, `globals`,
eslint-config-prettier` — the same versions the member that already lints uses. ONE
`npm install` at the root updates the lockfile; hoisting means members get no local
`node_modules` and their scripts still resolve the binary from the root `.bin`.
- Leave stale nested lockfiles inside members alone — `npm ci` at the root uses the root
lockfile, and the nested ones are pre-monorepo leftovers.
- Prove the lockfile is CI-ready without touching `node_modules`: `npm ci --dry-run` at the
root exits 0 only when every member's `package.json` agrees with the root lockfile — the same
assertion CI's `npm ci` makes before it runs the new lint step.

## 3. Inventory and partitioning

```bash
eslint src -f json > /tmp/lint.json    # from the member directory
node -e "
const r=require('/tmp/lint.json');
for(const f of r){ if(!f.messages.length) continue;
  const t={}; for(const m of f.messages){const k=m.ruleId||'parse'; t[k]=(t[k]||0)+1;}
  console.log(f.filePath.split('/').pop(), f.messages.length,
    Object.entries(t).sort((a,b)=>b[1]-a[1]).map(([k,v])=>v+' '+k).join(', '));
}"
```

Never read the raw report; tally it. Partition one writer per file — a three-digit count earns
its own child, single-digit files are batched into one child.

## 4. Rule triage

| rule | root cause | fix direction |
|---|---|---|
| `no-explicit-any` | explicit `any` | the library's real type, or `unknown` + a narrowing guard |
| `no-unsafe-member-access` / `-assignment` / `-argument` / `-return` / `-call` | an `any` upstream of the value | fix the `any`, not the use site — the cluster clears at once |
| `no-unnecessary-type-assertion` | an `as X` the compiler did not need | delete the assertion, then re-run `tsc`: the rule is right, but surrounding code may lean on the cast |
| `no-unused-vars` | dead import/local, or a callback parameter | delete genuinely dead code after grepping for references; `_`-prefix only where the signature is a contract |
| `consistent-type-imports` | type imported as a value | `import type` (mandatory under `verbatimModuleSyntax`) |
| `require-await` | `async` with no `await` | drop `async`, or await the real operation |
| `unbound-method` | method passed unbound | wrap in an arrow or bind it |
| `no-redundant-type-constituents` | `any \| X`, `unknown \| X` | collapse to the wider constituent |
| `prefer-const` | `let` never reassigned | `const` |

## 5. Replacing `any` on an interface member with heterogeneous implementations

A tool/handler interface often carries `function: (args: any) => Promise<unknown>` because each
implementation takes its own argument shape while the caller passes parsed JSON. Typing that
parameter `unknown` then breaks every assignment under `strictFunctionTypes`: a property-style
function type checks parameters contravariantly, so `(args: { url: string }) => ...` stops
being assignable to `(args: unknown) => ...`. Declare the member with METHOD syntax instead —
method parameters are checked bivariantly, which is exactly the assignability `any` provided,
with no `any` in the signature:

```ts
function(args: unknown): Promise<unknown>;   // bivariant: narrower implementations still assign
```

Keep the caller's `unknown` payload — it is honest, the arguments come from `JSON.parse`. Do
NOT "fix" the mismatch by re-adding `as unknown as Tool` at every call site: that restores the
casts the sweep just removed, and the next run flags them again once the shared type tightens.

Merge-order consequence: casts that were genuinely unnecessary while a shared type said `any`
become necessary — or error — the moment that shared package is tightened. Merge the shared
package FIRST, re-run each consumer's typecheck on the integration branch, and fix forward
there. Wave mechanics: `parallel-agent-worktrees`.

## 6. Per-child verification (in a worktree)

- Per-file signal: `eslint <own files>` exits 0 with no output; tally with `-f json` when you
need counts. `-f unix` is NOT an option — core ESLint removed that formatter in v10 and asking
for it exits 2 with a formatter error no matter what the file's state is (children will
otherwise report the tool as broken instead of reporting their result). Linting the whole
`src` in a worktree also reports siblings' unfixed files — expected, and never a reason to
edit them.
- Whole-program regression: `tsc --noEmit` still exits 0. Removing an `as` can surface a type
error elsewhere in the same file.
- Silencing audit on the merged diff:
`git diff <base>..<branch> | grep -nE 'eslint-disable|@ts-ignore|@ts-expect-error|as any'` —
an empty result is the requirement.
- Type-only cleanup must not change behaviour: no renamed exports, no reordered logic, no
dropped fallbacks. `catch (e: any)` becomes `catch (e)` plus `unknown` narrowing, not a
narrower catch type that changes which errors are handled.
