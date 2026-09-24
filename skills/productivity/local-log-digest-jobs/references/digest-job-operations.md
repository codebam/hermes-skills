# Digest-job operations: settling open vs closed, and re-running a job

Companion to the `local-log-digest-jobs` umbrella. The umbrella covers building
the collector and wiring the cron job; this file covers the two things that
decide whether the delivered digest is *trusted*: resolving stale claims, and
what to do when the user says "show me again".

## Second pass — the scan is a candidate list, not a finding

A bounded scan surfaces promising items; it does not know which are still open.
Logs assert completion as loudly as they assert breakage ("Done — built,
deployed, and tested against production") and log claims age fast: a "not
pushed" note written at 23:30 is usually stale by 09:00.

Three cheap moves resolve nearly every ambiguous item.

### 1. Read the tail of the specific source

For each ambiguous source, print only its last 1-2 assistant `text` blocks. The
verdict is almost always in the final message, and the tail costs a fraction of
the file. Generic shape:

```bash
zstd -dc -- "$log" 2>/dev/null | jq -r '
    select(.type=="assistant/message")
    | [ .data.message.content[]? | select(.type=="text") | .text ] | join(" ")
    | select(length>0) | gsub("[\\n\\r\\t]+";" ") | .[0:700]' | tail -2
```

What that pass actually caught in practice:

- a "broken feature" item was **fixed and pushed** hours earlier ("Found and
  fixed it… extracted the dialogs into `CampaignDialogs.tsx`") — but the same
  message ended "Still not deployed — run `pnpm deploy`", so the *deploy* was
  the real open item;
- a deploy item was **closed** ("Done — built, deployed, and tested against
  production"), so it had to be dropped rather than carried;
- a source with `0` assistant `text` blocks was a **user question that was
  never answered** — an open loop that no amount of git checking would reveal.

### 2. Verify state with the tool that owns it

Sweep every repo named in the scan in one script: `git -C <dir> status -sb` for
a dirty tree, and `git -C <dir> log --oneline @{u}..HEAD` for unpushed commits
(skip when `rev-parse --abbrev-ref @{u}` fails — no upstream). In one session
this retired five stale "not pushed" items at once *and* surfaced an
uncommitted `flake.lock` no session had mentioned. Print only what the command
returned; never restate a log claim as current fact.

### 3. Drop the closed items, and say so

Listing finished work destroys the user's trust in the channel faster than a
short digest does. When a dropped item is informative, name it in one clause
("the `c805a80` commit is pushed now") so the drops read as verification rather
than omission.

## Re-running a job when the user asks "show me again"

- **A running job refuses a second trigger.** `cronjob(action="run")` while an
  attempt is in flight returns, with no error:

  ```json
  {"executed": false,
   "execution_skipped": "Job is already running (a scheduler tick or another
    manual run is executing it); not started again."}
  ```

  So "fire it once more" is not available back-to-back — and a job whose script
  takes ~30s plus a reasoning pass is in flight for a while.
- **To show output immediately, reproduce the pipeline in-conversation**: run
  the collector script yourself and apply the same prompt instructions to its
  output. It is the same pipeline, so the shape is honest, and it lets you read
  the payload with your own eyes before the job's version lands.
- **Re-fire after it lands, with transient context.** When the job uses
  `continuity=True`, pass the `prompt` argument of `run` to say this is a manual
  re-run minutes later. Without it the job treats its own previous delivery as
  "yesterday's" digest and stamps items with nonsense ages ("open since now").
  Transient `prompt` context applies to that single fire and is never persisted.
- Tell the user which message is which: the in-conversation reproduction, the
  job's own delivery, and any re-fire are three separate messages.

## Mechanics worth knowing when wiring these jobs

| Fact | Value |
|---|---|
| Pre-run `script` timeout | 3600s default (`cron.script_timeout_seconds`) |
| Agent budget | inactivity-based, 600s default (active tool calls reset it) |
| Delivery framing | header/footer wrapper unless `cron.wrap_response: false` |
| Silence from a job | `[SILENT]` in the final response suppresses delivery |
| Scope of `continuity` | the job's own most recent output, injected next run |
| Scope of `attach_to_session` | makes a reminder reply-able; thread-preferred, DM falls back to mirroring |
