# DeepSeek Harness (dsh) session logs — layout and extraction

Session-specific detail for the `local-log-digest-jobs` umbrella. Verified
against the logs on this machine: 40+ active sessions/day, ~205 MB compressed
across 7 days.

## Layout

```
~/.dsh/
  sessions/<cwd-slug>/<session-id>/session.v3.jsonl.zstd   # zstd JSONL, one event per line
  sessions/<cwd-slug>/<session-id>/session.jsonl.zstd      # legacy form, same dir
  sessions/<cwd-slug>/<session-id>/session.lock            # lock, ignore
  task-board/ledger-v2.json                                # task board — was EMPTY (revision 0)
  task-board/scheduler-v2.json                             # {timeZone: America/Toronto, ledgerId}
  thinking-auditor/audit.jsonl                             # @codebam/dsh-thinking-auditor verdicts, 0600
  settings.yaml, profiles/<name>/, cordis.patch.yml, storages/, skills/
```

- The cwd slug is the working directory with `/` replaced by `-` and wrapped in
  `--`: `--persistent-etc-nixos--` → `/persistent/etc/nixos`. Useful as a
  fallback when the header's `cwd` is absent.
- One session dir can hold **both** a legacy and a v3 log — dedupe by
  directory and prefer `session.v3.*`, or every session is counted twice.
- File mtime equals the last event's timestamp exactly (checked across 25
  sessions, delta 0s), so mtime is a valid cheap recency filter/ordering key.
- There is no live "current session" marker beyond `session.lock`; a log whose
  last event is not `turn/end` was abandoned mid-work — a strong
  "possible unfinished task" signal.

## Event schema (`session.v3.jsonl`)

Every line: `{"type": ..., "seq": N, "time": <ms epoch>, "data": {...}}`.
Type counts from one 1395-event session: `session-log-deepseek/delivery-accepted`
225, `step/start` 224, `step/end` 224, `assistant/message` 224, `tool/result`
220, `tool/call` 220, `agent/inbox/spliced` 20, `user/message` 12, `turn/start`
7, `turn/end` 7, `session/title` 2, `request/header` 2.

| type | where the content lives |
|---|---|
| `session` (first line only) | `.cwd` — **top level**, next to `.id`, `.createdAt`, `.version`. NOT under `.data`. |
| `session/title` | `.data.title` (fallback title, then LLM-generated title) |
| `user/message` | `.data.content[]` blocks (`{type:"text",text}`); `.data.source.kind` |
| `assistant/message` | `.data.message.content[]` blocks: `reasoning` (the CoT), `text` (final answer), `tool-call`. Also `.data.usage`. |
| `tool/call` | `.data.name` (e.g. `bash`), `.data.callId`, `.data.arguments` |
| `tool/result` | `.data.message.content[0]`: `{type:"tool-result", toolCallId, isError, content:[{type:"text",text}]}` |
| `turn/start`, `turn/end`, `step/start`, `step/end` | turn/step counters only |

**Signal/noise:** `user/message` also carries machine-injected turns —
`source.kind` values seen: `user` (real prompt, has `rpcId` +
`clientTimeZone`), `plugin` (system prompt), plus `agent-instructions` and
`skill-catalog` turns. Filter to `source.kind == "user"` or the digest fills
with fake requests. `assistant/message` reasoning blocks are the bulk of the
bytes; only the `text` blocks are the model's answer to the user.

## Working extraction program

One `zstd -dc` into a spool, one `jq` pass emitting TSV (`@tsv` escapes
newlines/tabs so each row is one line), then `awk -F'\t'` for grouping,
per-kind caps and section headers. Times stay raw epoch seconds and are
formatted with gawk `strftime` (local TZ); jq's `strftime` is UTC.

```jq
def txt:  [ .data.content[]?         | select(.type=="text")      | .text ] | join(" ");
def atxt: [ .data.message.content[]? | select(.type=="text")      | .text ] | join(" ");
def rtxt: [ .data.message.content[]? | select(.type=="reasoning") | .text ] | join("\n");
def tstamp: (.time // 0)/1000|floor;
def clip(n): if (.|length) > n then .[0:n] + " …" else . end;
def clean: gsub("[\\n\\r\\t]+";" ") | gsub("^ +| +$";"");
def deblock: gsub("```[^`]*```";" [code block] ");   # fences eat the budget, not the signal

select(.type=="session" or .type=="session/title" or .type=="user/message"
       or .type=="assistant/message" or .type=="tool/call" or .type=="tool/result")
| .type as $t | tstamp as $ts
| if $t=="session" then ["HDR", 0, (.cwd // .data.cwd // "?")] | @tsv
  elif $t=="session/title" then (.data.title // "") as $ti
    | select(($ti|length)>0) | ["TITLE", 0, ($ti|clean|clip(120))] | @tsv
  elif $t=="tool/call" then ["CALL", 0, (.data.callId // "?") + "\u0001" + (.data.name // "?")] | @tsv
  elif $t=="tool/result" then
    (.data.message.content[]? | select(.type=="tool-result" and .isError==true)
     | ([.content[]? | .text // ""] | join(" ")) as $er
     | select(($er|length)>0)
     | ["ERR", $ts, ((.toolCallId // "?") + "\u0001" + ($er|deblock|clean|clip(400)))] | @tsv)
  elif $t=="user/message" then
    select(.data.source.kind=="user")
    | (txt|deblock|clean|clip(500)) as $u | select(($u|length)>0)
    | ["USER", $ts, $u] | @tsv
  elif $t=="assistant/message" then
    ([ atxt | deblock | clean | clip(700) | select(length>0) ] as $a
     | [ rtxt | split("\n")[] | select(test($markers;"i")) | clean | clip(200) ]
       | unique | .[0:6] | map(select(length>0)) as $todo
     | if ($a|length)>0 then ["ASSIST", $ts, ($a[0])] | @tsv else empty end,
       ($todo[] | ["TODO", $ts, .] | @tsv))
  else empty end
```

`$Markers` (reasoning filter for leftover work):

```
TODO|FIXME|XXX|not yet|haven.t|have not|didn.t (finish|complete|verify|commit|push)|
did not (finish|complete|verify|commit|push)|unfinished|still (need|have|open|pending|not)|
remaining|left to do|next session|next step|follow[ -]?up|unverified|incomplete|blocked|
waiting on|you (should|need to|may want|might want|can)
```

In awk, `CALL` rows build `name[callId]` so `ERR` rows can be labelled with the
tool name; join on `\u0001` and `split()` it. Keep per-kind caps (last 14 USER,
10 ASSIST, 6 ERR, 6 TODO) and print USER → ASSISTANT → ERRORED TOOL RESULTS →
TASK MARKERS, because that reading order matches "what was asked → what
happened → what broke → what's left".

## The live artifact

`~/.hermes/scripts/dsh-task-scan.sh` — implements the above with the two-tier
budget. Knobs (env, all optional):

| var | default | meaning |
|---|---|---|
| `DSH_HOME` | `$HOME/.dsh` | harness home |
| `DSH_SESSIONS_DIR` | `$DSH_HOME/sessions` | log root |
| `DSH_TASK_WINDOW_HOURS` | 48 | mtime window for candidate logs |
| `DSH_TASK_MAX_SESSIONS` | 60 | newest-first cap |
| `DSH_TASK_MAX_CHARS` | 22000 | whole-payload cap |

Measured: 60 sessions / ~60 MB compressed → ~27s wall, ~22 KB payload
(8 sessions in detail, 33 stubs, 19 dropped for size at 48h).

Wired to cron job `dsh daily task reminder` (`e9e4703ee70a`), `0 9 * * *`,
delivered to the origin chat, with `continuity=True`, `attach_to_session=True`,
and `enabled_toolsets=["terminal","file"]` so it can verify `git -C <dir>
status -sb` / `@{u}..HEAD` claims about unpushed work before reporting them.
