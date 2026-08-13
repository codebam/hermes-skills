---
name: github-repo-renaming
description: "GitHub repo renames/swaps with clone remote updates."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [GitHub, Repositories, Git, Renaming, Remotes]
    related_skills: [github-auth, github-repo-management]
---

# GitHub Repository Renaming & Swapping

## When to Use

- Renaming a GitHub repo and updating its local clone(s).
- Swapping the names of two repos (e.g., retiring an old name to make room for a new one).
- Any workflow where the GitHub-side name changes and every local remote must stay correct.

Rename a repo on GitHub, or swap two repos' names, while keeping every local clone's remotes pointing at the right place.

## Prerequisites

- Authenticated with GitHub (see `github-auth` skill)
- `gh` available and logged in (`gh auth status`)

## Renaming a Single Repo

`gh repo rename` updates the name on GitHub only — it does NOT touch any local remote URLs. Every clone needs its `origin` updated separately.

```bash
# Rename on GitHub
gh repo rename new-name -R owner/old-name --yes

# Update THIS local clone's origin (SSH form shown; match the existing protocol)
git remote set-url origin git@github.com:owner/new-name.git

# Any OTHER machines/clones must be updated too
```

Verify: `gh repo list --limit N` (or `git remote -v` locally).

## Swapping Two Repos' Names (old A -> legacy, current B -> A)

Order matters so a name is always free:

1. **Rename the retiree first** — frees the desirable name before you claim it.

```bash
gh repo rename old-name-legacy -R owner/old-name --yes     # frees 'old-name'
gh repo rename new-name -R owner/current-name --yes        # claims it
```

   Renaming the incumbent to the new name first may be rejected by GitHub because the target name is still taken.

2. **Update every local clone's remotes.** A repo can have multiple clones (different machines, or several remotes in one clone). Inspect each one before editing:

```bash
git -C /path/to/clone remote -v | cat
```

   Renames are pure URL swaps — map old-name -> new-name and update each remote:

```bash
git -C /path/to/clone remote set-url origin  git@github.com:owner/newname.git
git -C /path/to/clone remote set-url viewport-c git@github.com:owner/old-name-name.git
```

3. Re-verify with `git remote -v | cat` — a clean final listing confirms all remotes are remapped.

## Pitfalls

- `gh repo rename` does not rewrite existing clone URLs. Missing the remote-update step leaves clones silently pointing at the wrong server (they'll warn/404 on next push).
- Remotes can differ across clones: one clone may use SSH, another HTTPS, and a clone can carry extra remotes (an alias remote pointing at the repo being renamed). Read `git remote -v` before assuming its shape.
- When swapping, verify the retiree's rename actually freed the name (run it, check exit, then rename the incumbent) rather than doing both blind.

## Verification

- `gh repo list --limit <n>` shows new names server-side.
- `git remote -v | cat` in every clone shows remapped URLs.