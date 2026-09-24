# Deploying and Verifying a Workers + Durable Objects App

What has to run after `wrangler deploy`, what does not, and what a live URL can and cannot
prove. Written for the Workers / Durable Object / R2 shape with no D1 binding.

## The deploy command

- Read the repo's `deploy` script first: it is usually `build && wrangler deploy`, so client
  assets and the Worker ship in one upload and there is no separate asset step.
- `wrangler deploy` uploads the LOCAL working tree, not a pushed commit. Deploying from a
  branch that is ahead of its remote works — say so explicitly when the operator expects the
  remote to match production.

## Two migration layers — know which one you are in

1. **Wrangler-level Durable Object migrations** — the `migrations` array of tags in the
   wrangler config (`new_sqlite_classes`, renames, deletes). The deploy applies these; they
   change only when a DO class is added, renamed, or removed. Adding a class without a new
   tag is the failure mode.
2. **In-DO SQL schema** — the app's own migration list, applied by a runner in the DO
   constructor and tracked in a migrations table inside that DO's storage. It runs lazily:
   once per DO instance, on the next request that instantiates it. Nothing to invoke, and with
   no D1 binding `wrangler d1 migrations apply` is not part of this shape at all.

State the consequence out loud when asked "is a migration needed?": a tenant untouched since
 the deploy still lacks the new table until its next request creates it.

## Adding scheduled work

- A cron trigger is config, not code you run: the `triggers.crons` entry plus the
  `scheduled()` handler ship with the next `wrangler deploy` and start firing on that
  schedule. Nothing to invoke by hand — and the schedule fires neither in local dev nor in the
  test runner.
- Keep the work in a plain `sweep(env, opts?)` function and make the handler a one-line
  adapter that awaits it: that is the only way to run the sweep by hand when a schedule
  misbehaves, and the cheapest way for a test to exercise it. The pool exposes no
  `SELF.scheduled()`, but a test can also call the exported handler's `scheduled()` directly
  with a fake event and a minimal `ctx` — do that when the adapter itself is worth covering.
- A sweep that deletes stored objects inherits the app's split: the storage layer returns the
  rows plus the object keys, and the caller deletes the blobs. Reuse the key format of the
  existing manual purge route rather than deriving one.

## Verifying the deploy actually landed

| Evidence | What it proves |
|---|---|
| `wrangler deployments list` | The truth: newest version and its timestamp. The authority. |
| Fresh build output and `.wrangler/tmp` touched | The deploy command ran locally — NOT that the upload succeeded. |
| An unauthenticated fetch of the deployed hostname | Only that something serves. An Access-protected host returns the same redirect for the old and the new version, so it cannot identify which build is live. |
| 403 "Access must be configured" instead of the Access redirect | The Worker serves but its Access secrets are missing — a different failure from a stale deploy. |
| The live bundle fetched through the Cloudflare API | Which features are IN the running build (marker grep) — the only way to prove WHAT is deployed, because deploys here carry no commit metadata. |

## Which build is live: fetch the running bundle

`wrangler deployments list` answers WHEN (UTC timestamps, oldest first — the newest deploy is
the LAST entry, so read the tail), `wrangler deployments status` names the current version —
but entries show `Message: -`, so neither says which features the build contains. Pull the
running script's own bytes and count markers only the new code carries (SQL table names, tool
names, header strings):

- `GET https://api.cloudflare.com/client/v4/accounts/<account>/workers/scripts/<name>/content/v2`
  returns the live bundle (multipart, often several MB). Plain `/content` answers 405 for
  module workers — use `/content/v2`.
- Auth without wrangler in the loop: the OAuth token wrangler already stored at
  `~/.config/.wrangler/config/default.toml`, account id from `wrangler whoami` or `GET /accounts`.
- Read-only wrangler/API access exists whenever the session's terminal runs on the host shell;
  sandboxed worktree children cannot reach it. The DEPLOY stays the operator's step — this is
  the verification half you can do yourself.
- Ready-made: `scripts/live-worker-markers.py <worker-name> <marker...>` (pass `-` as the name
  to read it from `./wrangler.jsonc`).

Never report "it's deployed" from a serving URL, or from your own build having run. State what
you verified (with observation time), name what only the operator can check, and give the one
command that settles it.
