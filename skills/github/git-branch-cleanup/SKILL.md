---
name: git-branch-cleanup
description: "Delete or clean git branches locally and on GitHub."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Git, GitHub, Branches, gh-cli, Repo-maintenance]
    related_skills: [github-repo-management, github-pr-workflow]
---

# Git Branch Cleanup

Delete/rename/clean git branches both locally and on the GitHub remote. Covers
the bulk-delete "keep only these" workflow and the `gh api` command-line
pitfalls that silently no-op.

## Prerequisites

- `gh` authenticated (see `github-auth` skill) if touching the GitHub remote.

## Bulk-delete: keep only a list (local + remote)

Order matters: delete local first, then remote via `gh api`, then prune & verify.

```bash
cd /path/to/repo
KEEP='^(main|fix-gtk-focus|feature-keep)$'        # adjust to your keep-list
OWNER_REPO=$(git remote get-url origin | sed -E 's|.*github\.com[:/]||; s|\.git$||')

# 1) Delete local branches (skip current branch + keep-list). -D forces unmerged.
git branch -D $(git for-each-ref --format='%(refname:short)' refs/heads/ | grep -vE "$KEEP")

# 2) Delete each origin branch via the GitHub API.
for b in $(git for-each-ref --format='%(refname:short)' refs/remotes/origin/ \
           | grep -vE "^origin/(main|fix-gtk-focus|feature-keep)$" \
           | grep -vE 'origin/HEAD|^origin$'); do
  name="${b#origin/}"
  gh api -X DELETE "repos/$OWNER_REPO/git/refs/heads/$name" --silent \
    && echo "deleted origin/$name" \
    || echo "FAILED origin/$name"
done

# 3) Prune stale local tracking refs, then verify the real state.
git remote prune origin
gh api repos/$OWNER_REPO/branches --jq '.[].name'   # live branches on GitHub
git branch                                       # local branches
```

## Pitfalls

- **`gh api` is NOT `curl`.** `gh api` rejects curl flags like `-o <file>` or
  `-w '%{http_code}'` with `unknown shorthand flag`. The request is then *not
  sent at all* — but if your script has `... || echo "done"` it looks like it
  ran. Always use `gh api ... --silent` and branch on the exit code with
  `&&`/`||`. This is the #1 silent-failure mode.
- **Comparing local vs remote.** A branch can exist locally but never have been
  pushed (so `git branch` shows it, `gh api .../branches` does not). A local
  delete "succeeds" with nothing to delete on GitHub. Verify by listing both.
- **Multi-remote repos.** `refs/remotes/<other-remote>/...` branches belong to a
  *different* repo (e.g. an old C-rewrite vs a smithay rewrite of the same
  project). Only enumerate `refs/remotes/origin/` (or whichever remote the user
  names) — don't touch other remotes' branches.
- **Worktree branches.** A branch checked out in a linked worktree (`git branch`
  shows it with a `+` prefix) cannot be deleted until its worktree is removed.

## Verification

- Live remote list: `gh api repos/$OWNER_REPO/branches --jq '.[].name'`
- Clean tracking refs: `git remote prune origin`
- Local: `git branch`
