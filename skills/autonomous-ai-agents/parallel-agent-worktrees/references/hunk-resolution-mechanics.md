# Hunk-Level Conflict Resolution Mechanics

How to resolve a conflicted file during integration without losing the hunks git already
merged. Classify and arbitrate the hunks per `merge-reconciler`; this file is the mechanics.
`<ours>` = the branch you are merging into, `<theirs>` = the branch being merged,
`<base>` = their merge base.

## 1. Extract the three sides

```bash
git show <ours-ref>:<path>   > /tmp/ours.ts
git show <base-ref>:<path>   > /tmp/base.ts
git show <theirs-ref>:<path> > /tmp/theirs.ts
```

In a halted merge `<ours-ref>` is `HEAD`, `<theirs-ref>` is `MERGE_HEAD`, and the base is
`git merge-base HEAD MERGE_HEAD`.

## 2. Rebuild the merge

```bash
git merge-file -p /tmp/ours.ts /tmp/base.ts /tmp/theirs.ts > /tmp/merged.ts
echo $?    # exit code = number of conflicts
```

Run this even when a merge is in flight: it is the recovery path when the working file was
already overwritten by a whole-file side-pick, and inspecting it costs nothing. `git merge
--abort` is not needed for that recovery and often refuses once resolutions are staged
(`Entry '<path>' not uptodate. Cannot merge.`) — write the rebuilt file into the working tree,
stage it, and finish the merge normally.

## 3. See the blocks before planning

```bash
node scripts/resolve-conflict-blocks.mjs --list /tmp/merged.ts
```

## 4. Write the plan

One entry per block, in file order. `null` drops both sides; a string replaces the block.
Build it programmatically when the text is long or tab-indented:

```js
// /tmp/plan.mjs
import fs from "node:fs";
const theirs = fs.readFileSync("/tmp/theirs-side.txt", "utf8").replace(/\n+$/, "");
const ours = fs.readFileSync("/tmp/ours-side.txt", "utf8").replace(/\n+$/, "");
export default [null, "\tcombined line", `${theirs}\n});\n\n\n${ours}\n`];
```

Two traps: a JSON plan cannot hold raw tabs (`JSON.parse` fails with "Bad control character
in string literal" — emit it with `JSON.stringify`, or use an `.mjs` module of template
literals), and never retype tab-indented code from a terminal transcript — extract it from
the side files.

## 5. Apply, then stage

```bash
node scripts/resolve-conflict-blocks.mjs /tmp/merged.ts <path> /tmp/plan.mjs
grep -n '^<<<<<<<\|^>>>>>>>' <path>    # must print nothing
git add <path>
```

## The shared-trailing-line case

When both sides appended at the end of a file, git can treat the file's final line (e.g. a
closing `});`) as common context and leave it OUTSIDE both sides of the conflict. Each side
then ends mid-construct, and the resolution has to close both:

```
<theirs block text>      # ends mid-object
});                      # the closer git pulled out of the conflict
<ours block text>        # also ends mid-object
<shared tail: }>         # closes the last construct
```

## Verify

- No markers remain and the file typechecks.
- Run the tests of BOTH sides' features. A resolution that drops one side's wiring still
  passes the other side's tests, so a botched merge surfaces as a failure in a feature you
  merged earlier — not in the one you were working on.
