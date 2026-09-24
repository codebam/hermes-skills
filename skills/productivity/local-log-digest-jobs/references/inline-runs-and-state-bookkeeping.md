# Inline runs and state bookkeeping

Companion to `local-log-digest-jobs`. Covers the case where the user does not
wait for the schedule, and the bookkeeping that makes an inline run and a
scheduled run interchangeable.

## "Just give me one right now"

When the user reports the delivery hasn't arrived and asks for the output now
("it didn't deliver right away in telegram. just give me one right now"), the
expected answer is **the content**, not an explanation of scheduling.

- Do not offer to wait for the run, do not fire the job again first, and do not
  narrate the timing. A scheduled run does its own verification pass and takes
  minutes; that is not what was asked for.
- **Reproduce the pipeline in-conversation**: run the same collector script and
  apply the same prompt instructions to its output. Same source, same shape,
  honest result — and it lets you read the payload yourself, which is where the
  stale-claim problems get caught.
- Mention the scheduled delivery in one clause so the user knows a second
  message may follow, and say if it covers the same topic.

## Topic-keyed state must record inline runs too

If the job's state is keyed by item id (a curriculum, a checklist, a topic
list), **an inline run must write the state row as well.** Reproducing the
output but skipping bookkeeping makes the next fire re-teach the identical
topic, which reads as the job ignoring its own history.

- **Dedupe by id, never by row count.** Two rows for one topic inflate any
  `lesson #n` counter derived from the row count and skew spaced-repetition
  triggers (`every 5th item`):

  ```bash
  awk -F'\t' 'NR==1{print; next} !seen[$2]++' state.tsv > t && mv t state.tsv
  ```

- **Collisions are expected, not an error.** An inline teach and the job's own
  fire can both append the same id; that is harmless once deduped, and only
  *stays* harmless if ids are stable. Renaming a topic id orphans its history
  and the topic comes back.
- **Reconcile against the delivery record** at
  `~/.hermes/cron/output/<job_id>/<timestamp>.md`. If the job covered the topic
  you just taught inline, say so rather than leaving the user to work out why
  the same lesson arrived twice.
- **Read the file before blaming the job.** In one session the job's fish-based
  lesson looked like a repetition bug; reading the output file showed it had run
  with a stale prompt/skill snapshot taken before the environment correction
  landed, and the collector and skill had been fixed afterwards. A prompt or
  skill edit is not retroactive to a run already in flight.
