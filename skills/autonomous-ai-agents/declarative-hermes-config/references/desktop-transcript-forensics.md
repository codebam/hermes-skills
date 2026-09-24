# Desktop transcript forensics: why a tool row shows no result

Depth for "the desktop shows the wrong thing for a stored or live session"
(class-level path: the upstream-bugs section of SKILL.md). Read
`~/.hermes/state.db` read-only (`sqlite3.connect('file:...?mode=ro', uri=True)`)
and compare against the pinned source; never mutate the live DB to test.

## Which read feeds which surface

| Read | Filter | Used by |
|---|---|---|
| Display | `active = 1 OR compacted = 1`, deduped by `display_order` — per identity the active row wins, then the newest id | the desktop transcript (REST `/api/sessions/<id>/messages?include_compacted=true`, page limit 120) and its hydration |
| Context | `active = 1` | the model's conversation history |
| Rewind debris | `active = 0 AND compacted = 0` | nothing — invisible to both |

`display_identity` / `display_order` are columns on `messages`; the display
read collapses the copies of one logical message onto the newest active copy.
A row left `active = 0, compacted = 0` while its sibling call row stays
visible is the "the call paints, the result does not" shape.

## Symptom -> mechanism

- **"Result unavailable" on a row that shows its command/args** — a stored
  call row whose result row is missing from the display set (debris), or a
  live stream whose `tool.complete` carried no result. The desktop paints
  `part.result === undefined && part.completedAt !== undefined` as that label
  (`apps/desktop/src/components/assistant-ui/tool/fallback-model/index.ts`);
  hydration and the turn-settle seal set `completedAt`.
- **"Result unavailable" on rows with no args, grouped as "Ran N commands"**
  — the child-session live mirror. A delegated child's activity reaches the
  gateway as `subagent.*` events on the parent sid; the gateway mirrors them
  onto the child sid (`tui_gateway/agent_callbacks.py`) as `tool.start` with
  `args: {}` and then, when the next tool starts, `tool.complete` with the
  same dict — no `result` key. Live-only and never persisted; the stored
  transcript is complete. Do not "fix" it by touching the store.
- **Missing or summarized history in a stored session** — rows stamped
  `active = 0, compacted = 0` that should have been archived as
  `compacted = 1`. The stamping bug is upstream-fixed; existing rows are not
  backfilled, so the session keeps the gap until those rows are repaired.

## Checks to run

- **Call/result pairing over the deduped display set**: rebuild the display
  read in SQL (group by `display_order`, pick `ORDER BY active DESC, id
  DESC`) and count tool_call ids declared by visible assistant rows with no
  visible tool row, and results with no visible call. Zero mismatches means
  the stored view is complete — the symptom is live-only.
- **Debris inventory**: for every `active=0, compacted=0` row record whether
  a visible row has the same content ("twin") and, for tool rows, the state
  of the assistant row declaring its `tool_call_id`.

## Running the pinned desktop code offline

Node >= 22 strips TypeScript, so the pinned `apps/desktop/src` modules run
directly once their imports resolve. In a scratch dir: copy `src` and
`apps/shared/src`; register an ESM loader that maps `@/...` to the copied
src (try `.ts` / `.tsx` / `/index.ts`, and swap a written `.js` specifier to
`.ts`), points `@hermes/shared` at a shim re-exporting only the symbols the
module under test uses, and stubs the few modules that drag npm deps or the
app store (`@/lib/media` is one). Then call `toChatMessages(payload)` from
`lib/chat-messages/hydration.ts` on the exact payload the desktop receives
(the REST rows, or DB rows projected to the same keys) and report every part
with `completedAt !== undefined && result === undefined`. This reproduces the
desktop's decision without launching it.

## Repairing debris rows (only when asked)

Un-hide only what is genuinely lost: content non-empty, no visible
same-content twin (twins are superseded copies — leave them dead), and for
tool rows a visible assistant row declares the call id. Match the declaring
call's state — `active = 1` when the call is active (keeps call and result
consistent for the model too), `compacted = 1` when the call is compacted.
Keep the id list and prior flag values as the rollback; re-run the pairing
check before and after, and expect triggers to recompute `display_order` on
update so the desktop picks the change up on its next read.
