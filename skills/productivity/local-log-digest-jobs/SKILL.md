---
name: local-log-digest-jobs
description: "Recurring digests mined from local logs; script + cron."
version: 0.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [cron, digests, logs, reminders, data-collection, jq, zstd]
    related_skills: [weekly-review-planning, hermes-agent, product-price-monitor]
---

# Local-Log Digest Jobs

Turn a durable **local** data source — agent session logs, CLI histories, state
DBs, transcript files — into a recurring, reasoned digest or task reminder
delivered on a schedule. The shape is always the same:

1. a **collector script** that reads and bounds the raw source into a
   compact, injection-safe text payload;
2. a **cron job** whose prompt turns that payload into judgement (open vs
   done, dedupes, ranking), not into transcription.

The whole point is that deterministic code does the mining (cheap, exact,
bounded) and the model does only the reasoning that needs a model.

## When to Use

- "Look over my <logs/history/sessions> and remind me of X every day at 9am."
- "Build a workflow that watches <local source> and pings me."
- "Summarize what I got done / left open from my agent sessions."
- A recurring reminder or digest must be derived from local files rather than
  the web.

Don't use for: live external sources (see `product-price-monitor`,
`blogwatcher`, `competitor-news-monitor`), one-off "what's in this log"
questions (just grep it), or a digest that needs no judgement — if the script
can print the exact message, make it a `no_agent` cron job instead.

## Phase 1 — Find the real source; never guess the schema

1. Locate the store *and its siblings* before deciding what to read. Look for
   the tool's own home dir, a state/ledger DB, and per-project subdirs. A
   plausible-looking store may be empty or stale — check revision/row counts
   and say so rather than building on it.
2. Confirm the actual serialization: compressed or plain, JSONL or one blob,
   which version suffix (`x.v3.jsonl.zstd` vs `x.jsonl.zstd`).
3. **Count the event/record types before writing extractors.** Decompress one
   real file and tally the type field; do not infer the schema from prose or
   from a doc. Sample one record of each type you intend to parse.
4. Separate *signal* from *noise* at the source. Logs carry machine-injected
   messages (system reminders, skill catalogs, instructions) next to real user
   turns — find the discriminator field (e.g. `source.kind == "user"`) and
   filter on it, or the digest fills with fake tasks.
5. Sanity-check any ordering assumption you rely on (file mtime as a proxy for
   recency) against the records' own timestamps before trusting it.

## Phase 2 — Build a bounded collector script

Put it at `~/.hermes/scripts/<name>.sh` (cron `script=` resolves relative to
that dir). Reference implementation:
`~/.hermes/scripts/dsh-task-scan.sh` — see `references/dsh-session-logs.md`.

- **One decompress, one parse.** Decompress each file once into a spool, then
  run a single `jq` pass over it that emits TSV rows. Re-running jq per field
  doubles the runtime on multi-MB logs.
- **Emit TSV via jq `@tsv`.** It escapes newlines/tabs inside fields, so every
  row stays one line and `awk -F'\t'` can parse it. For sub-fields (an id plus
  its payload) join with `\u0001` and `split()` it back out in awk.
- **Format times in gawk, not jq** (see Pitfalls) — emit raw epoch seconds.
- **Cap per kind, per record** (e.g. last 14 user lines, 10 assistant lines,
  6 errors), keeping the *most recent* items, then print them in a fixed
  section order. Logs are unbounded; digests must not be.
- **Two-tier output so coverage survives the cap.** Give the newest N sources
  full detail under a detail budget (60% of the payload, with a per-source
  cap), and everything older a one-line stub under the remaining budget;
  count what you dropped and say so in a trailing summary line. A flat cap
  silently lops off the tail (usually the older, still-open items).
- **Knobs via env vars with defaults** (`<TOOL>_WINDOW_HOURS`,
  `_MAX_SOURCES`, `_MAX_CHARS`) so a test run and the production run differ by
  env, not by editing the script.
- **Assert dependencies at the top** (`zstd`, `jq`, `awk`, `find`) with a
  clear message, and exit 0 with a human sentence when the source is missing —
  an empty scan is a valid result, not an error.
- Give the payload a header (when it ran, window, how many sources) and a
  footer legend explaining what each section means. The model reading it has
  no other context.

## Phase 3 — Wire the cron job

```
cronjob(action="create",
        name="<what it is>",
        schedule="0 9 * * *",            # or "every day 9am"
        script="<collector>.sh",         # stdout is injected into the prompt
        prompt="<self-contained extraction + formatting instructions>",
        continuity=True,                 # carry yesterday's digest forward
        attach_to_session=True,          # replies to a reminder continue it
        enabled_toolsets=["terminal", "file"])
```

- **`continuity=True` is the dedupe mechanism.** Instruct the prompt to use a
  prior digest (when present) to age items ("open since Mon") and to drop
  items now done — otherwise the same five tasks arrive every morning.
- **Give it `terminal`, not `file` alone, when the prompt verifies claims**
  (e.g. `git -C <dir> status -sb`, `@{u}..HEAD`) so it can confirm a stale
  "not pushed" line instead of repeating it. Cap that verification (~6 repos,
  short timeouts, skip on error).
- **Restrict toolsets** — a mining job needs no `browser`/`delegation`; the
  schemas are paid for on every LLM call.
- **Prompt must be self-contained**: it runs in a fresh session with no chat
  context. Name the source, what each section means, what to keep, what to
  drop, the ranking, the output format, the length cap, and "never invent an
  item; if nothing is open, say so in one line". It cannot ask questions.
- Deliver to `origin` for a personal reminder; the wrapper/framing is a config
  concern (`cron.wrap_response`), not something the prompt should mention.

## Phase 4 — Verify end-to-end

1. `bash -n <script>` for syntax, then run it standalone with *small* knobs
   (`MAX_SOURCES=6 MAX_CHARS=8000`) and read the real output. Confirm cwd,
   timestamps, and section headers are populated, not `?` or empty.
2. Run it once with production defaults; check runtime fits comfortably inside
   the cron script timeout (default 3600s) and the payload is under the cap
   with the summary line intact.
3. `cronjob(action="run", job_id=...)` for a live end-to-end fire and confirm
   the delivered message's shape — the test run also seeds continuity.
4. Report the first fire time back to the user in their local zone.

## Output shape (this user)

Group by project/repo with short bold headings, one bullet per item, each with
a compact evidence/age parenthetical, ≤ ~1800 chars for a Telegram digest, and
end with a single `**Start here:**` pick. Grouped sections are what land with
this user; a flat list does not.

## Pitfalls

- **awk field assignment silently corrupts tab-delimited pipelines.** Writing
  `sub(...)`/assigning `$2` makes awk rebuild `$0` with `OFS` (a space) — the
  tabs vanish, downstream `cut -f4-` returns empty, and the whole pass yields
  nothing with exit 0. Copy fields into plain variables (`p = $2; sub(...)`)
  and print explicit `\t` separators; check `cat -A` on a sample row.
- **jq's `strftime` emits UTC; gawk's is local.** Emitting formatted times
  from jq showed every event 3-4h off (UTC vs America/Toronto). Emit raw epoch
  seconds and format with gawk `strftime`, or `date -d @<epoch>`.
- **A schema guess costs a whole debugging cycle.** `cwd` was top-level on the
  session header, not under `data` like every other event — one `jq -r '.data.cwd'`
  returned `null` and printed `?`. Probe the record once; add a fallback
  (derive the path from the directory name) instead of trusting one field.
- **Truncation hides sources, not just lines.** Enforce a budget when you
  decide to emit, not at the end with `head -c`, or the tail sources and the
  summary line disappear while counts still claim they were processed.
- **Huge inline shell one-liners get blocked** by the command guard
  ("oversized/unparseable inline payloads" — awk bodies with braces, heredocs).
  Write the script with `write_file` and run `bash <path>`; don't retry the
  same inline payload reworded.
- **Don't assume the obvious store is the task source.** A task-board/ledger
  file can be present but empty (`revision: 0`, `tasks: []`) — read it, then
  build on the evidence that actually exists.
- Stubs that are all noise (sessions with no user turns) still cost budget —
  render them as an ~80-char one-liner or skip them.
- Deleting spool/temp files only in a `trap` after the loop means a mid-run
  failure leaks them; clean per iteration as well.

## Verification

- [ ] The schema was read off a real record of each type, not inferred.
- [ ] Signal/noise discriminator applied (machine-injected messages excluded).
- [ ] Standalone run reviewed with real data: sections populated, times correct
      in the user's local zone, ordering matches record timestamps.
- [ ] Payload under the cap with the trailing summary/legend intact.
- [ ] Job created with `script`, self-contained prompt, toolsets restricted,
      `continuity` set, and a live `cronjob(action="run")` observed.
- [ ] `~/.hermes/scripts/` path and all script dependencies assert cleanly.

## Support files

- `references/dsh-session-logs.md` — DeepSeek Harness (dsh) session-log layout,
  event schema, the working jq/awk extraction program, and the live
  `dsh-task-scan.sh` knobs.
