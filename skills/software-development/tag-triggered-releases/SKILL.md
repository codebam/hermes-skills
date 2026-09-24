---
name: tag-triggered-releases
description: Use when cutting release tags that fire CI deploys.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [git, tags, release, ci, submodules, deploy]
    related_skills: [parallel-agent-worktrees, github-repo-management, cloudflare-workers-testing]
---

# Tag-Triggered Releases

For repos where CI fires a **deploy from a tag** instead of a branch push — typically a
submodule monorepo with per-component tag series (`bot-v*`, `webapp-v*`) and a workflow that
checks out submodules recursively at the tagged commit. "Cut the release" means: pick the right
components, number them from the remote, create the tags, and push in an order the workflow can
actually check out.

## When to Use

- The user asks to "make new tags", "cut a release", or "tag so we can deploy".
- A workflow in the repo triggers on tags (`on: push: tags: ['*-v*']`) and you need to know
  what to create and in what order to push it.
- You are in a submodule monorepo where the deploy checks out submodules recursively at a
tagged superproject commit.
- You have to prepare a release in a session that cannot push (no credentials) and hand the
  user the exact commands.

## Procedure

1. **Read the repo's release script before typing a single git command.**
   Repos of this shape usually ship one (`scripts/release.sh`, `make release`) and its header
documents the triggers and the push order — the authoritative answer, unlike a reconstruction
from the workflow file. Running it also gets you: a fetch first (the remote is authoritative for
numbering), refusals on dirty worktrees / stale branches / already-existing tags, the same
checks CI runs, and a per-component patch bump. Flags worth looking for: `--no-push` (create
locally, print the push order), `--no-fetch` (offline), `--dry-run`, `-y`, `-n/--no-sign`.
   - A signing-by-default script **dies** when no GPG key is available; that is the cue to
     `--no-sign` and to disclose that the tags are annotated, not signed.
2. **Number from the remote, never from a tag listing.**
   - `git fetch --tags` first. If you cannot fetch (no credentials), say so and give the
     last-fetch time the number was computed from — never present a stale number as current.
   - **Never read the next version off `git tag --list | tail`**: tag names sort
     lexicographically, so `v12.6.99` sorts *after* `v12.6.100` and the tail shows an old tag.
     Sort by version fields:
     `git tag -l '<prefix>[0-9]*' | grep -E '^<prefix>[0-9]+\.[0-9]+\.[0-9]+$' | sort -t. -k1,1n -k2,2n -k3,3n | tail -1`,
     or let the release script compute it.
   - Series are per component and their counters drift apart. Tag only components whose code
     changed — **including a workspace-shared package compiled into a component's bundle**. A
     tag on an unchanged component redeploys identical behaviour; skip it and say why.
3. **Push in dependency order.**
   1. submodule branch(es) — the workflow's checkout is `submodules: recursive`, so the commit
      pinned by the tagged superproject commit must already exist on the submodule remote;
      tagging first fails the checkout.
   2. superproject branch — records the new gitlink, and pushing it may itself be a trigger
      (commonly a dev/staging deploy; say so).
   3. the tag last — that is the production deploy.
4. **When you cannot push, hand off instead of improvising.** No credentials is a normal state,
   not a failure: cut the tags with the script's no-push mode and report the commands **in
   order with the reason for the order**, plus the caveats — numbering unverified since the
   last fetch (name the time), tags annotated rather than GPG-signed and the command to redo
   them signed, and which components got no tag. Never push, and never re-tag, on the user's
   behalf when credentials are absent: their host is the authority.
5. **Verify the tag you actually created before reporting it.**
   `git cat-file -t <tag>` (expect `tag`), `git tag -n99 -l <tag>` for the message,
   `git log -1 --format='%h %s' <tag>^{}` for the commit, and
   `git ls-tree <tag>^{} <submodule> <submodule>` to confirm the gitlinks match the branches
   about to be pushed. Report that evidence, not the intention.

## Rules

- **"Make tags we can push" means create and stop.** Push only when the user asks for the push
  itself; otherwise end with the ordered commands.
- Tag the components whose behaviour changed, and only those. A no-op redeploy is noise the
  user has to reason about later.
- The tag message is the release's changelog line — write what shipped, not the subject line of
  whatever commit happens to be HEAD (the release script's default is `"<tag>: <HEAD subject>"`,
  which is often a docs or chore commit).
- Run the repo's gate on the integration tree before tagging (or let the release script run its
  checks) rather than skipping them with `--skip-checks`.
